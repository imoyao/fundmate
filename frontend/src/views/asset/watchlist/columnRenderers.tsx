/**
 * watchlist 自选表格单元格渲染器注册表
 *
 * 对应 issue #995（umbrella #1022）。
 * 与 columnDefs.ts 配套：模板 v-for 列定义，按 def.renderer 分发到本文件的函数式组件。
 *
 * 核心职责（设计文档 §4）：把 index.vue 模板里散落的
 *   v-if="realtimeEnabled && getValuationItem(row.symbol)"
 * 双分支「实时覆盖静态」逻辑，内聚进 money/riseFall renderer，模板不再出现双分支。
 *
 * 约束（AGENTS.md / realtime-data-sources.md）：不得在此新开 JSONP 通道；
 * 实时数据一律来自 ctx.getValuationItem（useRealtimeQuotes 链路）。
 *
 * ── 维护者须知 ──
 * #995 步骤 3 已完成：index.vue 已切换到全量 columnDefs 驱动，
 * product/actions 均由本注册表渲染（selection 因 type="selection"
 * 无法 renderer 化，仍由 index.vue 模板按 batchMode 注入）。
 * 后续改 product/actions 交互只需改本文件，不再有 index.vue 模板副本。
 *
 * #1281 第四轮（2026-09-04）：独立 marker 列已取消，置顶 / 特别关注的状态标记
 * 内联到 product 列名称前（renderRowMarks），点击即切换；操作列同步精简为单个
 * 「移除」按钮。
 */

import { h, type FunctionalComponent, type VNode } from "vue";
import { ElButton, ElTooltip } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import MoneyWithRatio from "@/components/MoneyWithRatio/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import { formatDate } from "@/utils/date";
import { pricePrecision } from "@/utils/pricePrecision";
import type { ColumnDef, ColumnRenderer, WatchlistRow } from "./columnDefs";
// renderer DOM 不携带页面 scoped 属性，配套样式必须随渲染器走（见 css 文件头注释）
import "./columnRenderers.css";

/** 实时估值项（与 useRealtimeQuotes.getValuationItem 返回结构一致） */
export interface ValuationItem {
  currentPrice?: number;
  changePct?: number;
}

/** 派生值结果（组合计算列，由 index.vue 注入计算函数） */
export interface DerivedValue {
  value: number;
  ratio: number;
}

/** 渲染上下文：承载页面级状态与方法（避免 renderer 直接耦合大组件） */
export interface RenderCtx {
  /** 是否开启实时估值 */
  realtimeEnabled: boolean;
  /** 取某 symbol 的实时估值项 */
  getValuationItem: (symbol: string) => ValuationItem | undefined;
  /** 全部标签（用于 product 列渲染 tag chips） */
  allTags: { id: number; name: string; color?: string }[];
  /**
   * 分组 id → 分组名（#993「所属分组」列）。
   * row.group_ids 只是 id 数组，名称映射属于页面级状态，故由 index.vue 注入，
   * renderer 不直接依赖 groups composable。
   */
  groupNames: Record<number, string>;
  /** 派生计算列的取值函数（注入 index.vue 的 addedReturnAmount 等） */
  derived: (
    kind: "addedReturn" | "marketValue",
    row: WatchlistRow
  ) => DerivedValue;
  /** 打开标签编辑弹窗（product 列 add-tag 按钮） */
  openTagEditor: (row: WatchlistRow) => void;
  /** 是否批量管理模式（true 时 actions 列显示 "-" 占位） */
  batchMode: boolean;
  /** 当前 hover 行的 key（row.id ?? row.symbol，由 index.vue @cell-mouse-enter/leave 维护）。
   *  操作列/产品列是 fixed 列，EP 固定列独立 DOM，CSS :hover 无法跨表同步，
   *  因此行 hover 淡入必须由 JS 行 hover 状态驱动（见 design.md 行内操作交互规范）。 */
  hoveredRowKey: string | number | null;
  /** 手动设置 hover 行状态（fixed 列自身 hover 时自驱动，避免依赖主表 mouseenter） */
  setHoveredRowKey: (key: string | number | null) => void;
  /** 操作回调（actions 列） */
  actions: {
    togglePin: (row: WatchlistRow) => void;
    toggleFavorite: (row: WatchlistRow) => void;
    remove: (row: WatchlistRow) => void;
    openNotesEditor: (row: WatchlistRow) => void;
  };
  /** 近 N 日收盘价序列（sparkline 列，#990）：symbol → close 数组；无数据的 symbol 键缺省 */
  trends: Record<string, number[]>;
}

/** 安全地从 row 取任意字段（WatchlistItem 无索引签名，需经 unknown 中转） */
function field(row: WatchlistRow, key: string): unknown {
  return (row as unknown as Record<string, unknown>)[key];
}

/**
 * 投顾组合平台枚举 → 中文（AdvisorPortfolio.platform）。
 * 后端存英文枚举（QIEMAN/DANJUAN/TIANTIAN/YINGMI），编号式枚举对用户无意义，
 * 展示层统一转平台名；未知值原样兜底（新增平台未同步映射时不至于空白）。
 */
const ADVISOR_PLATFORM_LABELS: Record<string, string> = {
  QIEMAN: "且慢",
  DANJUAN: "蛋卷基金",
  TIANTIAN: "天天基金",
  YINGMI: "盈米"
};

/** 组合类标的（非交易实体）：资产类型层面的判定，与后端 asset_types 单一来源对齐。
    这类标的没有对外有意义的交易代码（股票/ETF/指数的 `# 代码` 才有意义），
    名称与第二行元信息是唯一的识别信息。 */
const COMPOSITE_ASSET_TYPES = new Set(["portfolio", "manager"]);

/** 取行的 asset_type（后端已归一为小写；历史行可能大写，统一 lower 兜底） */
function assetTypeOf(row: WatchlistRow): string {
  return (
    (field(row, "asset_type") as string | null | undefined) || ""
  ).toLowerCase();
}

/** 行是否为投顾组合/基金经理等组合类标的 */
function isCompositeAsset(row: WatchlistRow): boolean {
  return COMPOSITE_ASSET_TYPES.has(assetTypeOf(row));
}

/**
 * 组装产品列第二行元信息，非组合类行返回空串不渲染：
 * - 基金经理：所属基金公司（后端 manager_company，如「易方达基金管理有限公司」）
 * - 投顾组合：平台 · 主理人 · 策略类型
 * 经理行没有交易代码、组合行的平台码对用户无意义，识别信息全由本行承担。
 */
function compositeSubMeta(row: WatchlistRow): string {
  if (assetTypeOf(row) === "manager") {
    return (field(row, "manager_company") as string | null | undefined) || "";
  }
  const platform = advisorPlatform(row);
  if (!platform) return "";
  return [
    ADVISOR_PLATFORM_LABELS[platform] || platform,
    field(row, "advisor_host") as string | null | undefined,
    field(row, "advisor_strategy_type") as string | null | undefined
  ]
    .filter((v): v is string => Boolean(v))
    .join(" · ");
}

/** 投顾组合平台枚举（后端 AdvisorPortfolio 回查命中时下发 platform） */
function advisorPlatform(row: WatchlistRow): string {
  return (field(row, "advisor_platform") as string | null | undefined) || "";
}

/** 解析某列应显示的「基础静态值」与「实时覆盖值」 */
function resolveValue(
  row: WatchlistRow,
  def: ColumnDef,
  ctx: RenderCtx
): { staticVal: number; realtimeVal?: number; useRealtime: boolean } {
  const staticVal = Number(field(row, def.key)) || 0;
  if (def.realtimeField && ctx.realtimeEnabled) {
    const item = ctx.getValuationItem(row.symbol);
    if (item && typeof item[def.realtimeField] === "number") {
      return {
        staticVal,
        realtimeVal: item[def.realtimeField],
        useRealtime: true
      };
    }
  }
  return { staticVal, useRealtime: false };
}

// ---- 各 renderer 实现 ----

/**
 * 迷你走势图（#990）：纯 SVG 折线，无坐标轴/网格/背景。
 * - 颜色随涨跌：首尾比较，涨 --color-rise / 跌 --color-fall（禁止硬编码 hex）；
 * - 数据缺失（未回填/场外基金/新标的）降级显示 --，不影响行高与布局；
 * - 不逐格实例化 ECharts：40 行同屏 40 个图表实例必卡（issue #990 决策）。
 */
const renderSparkline: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = props => {
  const series = props.ctx.trends[props.row.symbol];
  if (!series || series.length < 2) {
    return h(
      "span",
      { class: "text-xs", style: { color: "var(--text-tertiary)" } },
      "--"
    );
  }
  // 迷你走势尺寸：宽 72 / 高 22。
  // 演进：96×24（原始）→ 64×20（#1281 第一轮压榨，在 40px 行高里仍偏高偏扁）
  // → 72×22（#1281 第二轮，行高回到 54px 后按视觉比例回调，线条有呼吸但不抢主数据）
  const width = 72;
  const height = 22;
  const pad = 2;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = max - min || 1; // 全平序列防除零
  const stepX = (width - pad * 2) / (series.length - 1);
  const points = series
    .map((v, i) => {
      const x = pad + i * stepX;
      const y = pad + (height - pad * 2) * (1 - (v - min) / range);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const rising = series[series.length - 1] >= series[0];
  const stroke = rising ? "var(--color-rise)" : "var(--color-fall)";
  return h("svg", { width, height, viewBox: `0 0 ${width} ${height}` }, [
    h("polyline", {
      points,
      fill: "none",
      stroke,
      "stroke-width": 1.5,
      "stroke-linejoin": "round",
      "stroke-linecap": "round"
    })
  ]);
};

const renderDate: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
}> = props => {
  const v = field(props.row, props.def.key);
  return h("span", { class: "text-sm" }, v ? formatDate(String(v)) : "--");
};

const renderMoney: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = props => {
  const raw = field(props.row, props.def.key);
  if (props.def.props?.nullable && (raw === null || raw === undefined)) {
    return h(
      "span",
      { class: "text-sm", style: { color: "var(--text-tertiary)" } },
      "--"
    );
  }
  const { staticVal, realtimeVal, useRealtime } = resolveValue(
    props.row,
    props.def,
    props.ctx
  );
  return h(MoneyDisplay, {
    value: useRealtime ? realtimeVal! : staticVal,
    precision: pricePrecision(props.row.asset_type),
    size: "sm"
  });
};

const renderRiseFall: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = props => {
  const { staticVal, realtimeVal, useRealtime } = resolveValue(
    props.row,
    props.def,
    props.ctx
  );
  return h(RiseFallText, {
    value: useRealtime ? realtimeVal! : staticVal,
    size: "sm"
  });
};

const renderQty: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
}> = props => {
  const v = Number(field(props.row, props.def.key)) || 0;
  const unit = field(props.row, "venue") === "OTC" ? "份" : "股";
  return h(
    "span",
    { class: "font-mono text-sm" },
    v > 0 ? `${v} ${unit}` : "--"
  );
};

/**
 * 纯文本 / 枚举映射列（#993 新增候选列）。
 * - 常规字段：直接取 row[key] 转字符串；
 * - 「所属分组」列（key="groups"）特殊：row.group_ids 是 id 数组，需经
 *   ctx.groupNames 映射为分组名；多分组以「、」连接，超过 2 个折叠为「等 N 组」，
 *   完整名单由 title 承载（避免撑宽列、与 #1281 密度目标冲突）。
 * 空值统一降级为 --（与 date / qty renderer 同语言）。
 */
const renderText: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = props => {
  const { row, def, ctx } = props;
  if (def.key === "groups") {
    const ids = (row.group_ids ?? []) as number[];
    const names = ids
      .map(id => ctx.groupNames[id])
      .filter((n): n is string => Boolean(n));
    if (names.length === 0) {
      return h(
        "span",
        { class: "text-sm", style: { color: "var(--text-tertiary)" } },
        "--"
      );
    }
    const shown = names.slice(0, 2).join("、");
    return h(
      "span",
      { class: "text-sm", title: names.join("、") },
      names.length > 2 ? `${shown} 等 ${names.length} 组` : shown
    );
  }
  const v = field(row, def.key);
  return h(
    "span",
    { class: "text-sm" },
    v == null || v === "" ? "--" : String(v)
  );
};

const renderMoneyRatio: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = props => {
  const { row, def, ctx } = props;
  // 派生列（持仓市值 / 添加后涨幅）：直接取注入的计算结果，布局为
  // 「金额在上、比例在下」两行（MoneyWithRatio 默认态）。
  // #1281 曾为压行高改为金额与比例同行内联，实测两个数字并排削弱主次、
  // 列内挤成一团（且把金额的「+」号也带了出来），用户明确不接受，故：
  // ① 布局回退为默认双行；② 金额展示参数恢复 #995 重构前的原模板语义（见
  //  pre-#995 index.vue）——市值不带正负号、占比中性色；添加后收益不带货币符号。
  if (def.derived) {
    const d = ctx.derived(def.derived, row);
    const isMarketValue = def.derived === "marketValue";
    return h(MoneyWithRatio, {
      value: d.value,
      ratio: d.ratio,
      moneySize: "sm",
      // 持仓市值：金额是余额不是涨跌 → 不带 +/- 号、保留 ¥ 符号
      // 添加后收益：金额由 price_at_added 差值计算，是真盈亏 → 带 +/- 号、不带 ¥
      showSign: !isMarketValue,
      showCurrency: isMarketValue,
      // 「持仓市值」的比例是市值占比（恒为正），非涨跌语义，必须中性色；
      // 「添加后涨幅」的 % 是真涨跌，保留默认涨红跌绿
      // （components.md MoneyWithRatio：占比等非涨跌语义 ratioAutoColor=false）
      ratioAutoColor: !isMarketValue
    });
  }
  // 直接字段列（持仓收益）：value=def.key, ratio=props.ratioKey
  const value = Number(field(row, def.key)) || 0;
  const ratioKey = (def.props?.ratioKey as string) || "change_pct";
  const ratio = Number(field(row, ratioKey)) || 0;
  const hasPosition = (Number(field(row, "holding_quantity")) || 0) > 0;
  return h(MoneyWithRatio, {
    value: hasPosition ? value : null,
    ratio: hasPosition ? ratio : null,
    moneySize: "sm",
    showSign: true,
    showCurrency: false
  });
};

const renderProduct: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = props => {
  const row = props.row;
  const ctx = props.ctx;

  /** 行是否可编辑：真实产品行（有 symbol）即允许显示「＋ 标签」入口；
     聚合/虚拟行（无 symbol 也无 id）不渲染，避免死按钮。
     注：此前仅用 row.id != null，但部分真实产品（草稿态 / 尚未落库 id）id 为 null
     仍应可加标签——放宽到 symbol 维度（2026-09-05 修复「有的行不显示 +标签」）。 */
  const editable = row.id != null || row.symbol != null;

  // 正常 product 列：两行紧凑布局 —— 第一行名称，第二行 代码 / 类型 / 标签文字 chips / 「＋ 标签」。
  // 演进（issue #1281 三轮）：
  //   ① 三行式（名称 / 代码+类型 / 标签 chips）→ 行高约 78px，一屏仅 3 行，信息量不足；
  //   ② 单行压扁式（名称+代码+类型+标签同行）→ 行高 40px，但长名称被挤成两三个字、不可读；
  //   ③ 两行紧凑 + 标签文字 chips → 行高 56px，名称完整可读、标签「见字」且可点击编辑，
  //      行数约为 ① 的 1.4 倍，是密度与可读性的平衡点（参考 jigu 自选表主列布局）。
  const tagIds = Array.isArray(row.tag_ids) ? row.tag_ids : [];
  // 与模板 findTagColor/findTagName(allTags, tagId) 语义等价的内联查找；
  // 找不到时 name 回退空串、color 回退中性 --text-tertiary
  // （design.md「数据色例外」：分组/标签色为用户数据，非设计令牌，缺失回退中性 token）
  const tagColor = (tagId: number) =>
    ctx.allTags.find(t => t.id === tagId)?.color || "var(--text-tertiary)";
  const tagName = (tagId: number) =>
    ctx.allTags.find(t => t.id === tagId)?.name || "";
  // 行 hover 状态（add-tag 按钮在 fixed:left 产品列内，:hover 无法跨固定列 DOM 同步，需 JS 状态驱动）；
  // 容器自身绑定 mouseenter/leave 自驱动，鼠标直接悬停产品列时也能亮起 add-tag 按钮
  const isRowHovered =
    ctx.hoveredRowKey != null && ctx.hoveredRowKey === (row.id ?? row.symbol);
  const rowKey = row.id ?? row.symbol;
  /** 第二行最多展示的标签 chip 数，超出折叠为 +N（title 列出全部标签名） */
  const MAX_TAGS = 2;

  /** 打开标签编辑弹窗（chip 点击 / 「+ 标签」按钮共用） */
  const openTagEditor = (e: Event) => {
    e.stopPropagation();
    ctx.openTagEditor(row);
  };

  /** 当前行的备注文本（空串＝未填写）——用于行内入口的「有无内容」状态 */
  const noteText = (field(row, "notes") as string) || "";
  /** 打开备注编辑弹窗（#1285）：与备注列共用同一 renderer action，不依赖备注列是否可见 */
  const openNotesEntry = (e: Event) => {
    e.stopPropagation();
    ctx.actions.openNotesEditor(row);
  };

  return h(
    "div",
    {
      class: ["product-row", { "is-row-hovered": isRowHovered }],
      onMouseenter: () => ctx.setHoveredRowKey(rowKey),
      onMouseleave: () => ctx.setHoveredRowKey(null)
    },
    [
      // 标签 chips / 「+ 标签」按钮经 #meta 插槽注入产品列第二行（与代码、类型同一弱化小字行）。
      // 标签必须「见字」——纯色点只剩色块没有语义，用户明确不接受（#1281 第二轮）；
      // chip 以标签数据色作底纹与描边、中性文字保可读，点击即编辑（hover 有反馈）。
      h(
        ProductDisplay,
        {
          compact: true,
          name: (field(row, "display_name") as string) || row.symbol,
          symbol: row.symbol,
          typeLabel: (field(row, "type_label") as string) || "",
          // 组合类标的的分层信息（经理→所属公司；投顾→平台 · 主理人 · 策略）独立成行，
          // 避免与代码/类型/标签挤一行（用户 2026-09-09 拍板）
          subMeta: compositeSubMeta(row),
          // 组合类标的（投顾组合 ZHxxxx/CSIxxxx、基金经理 MGR_<mgr_code>）的编码对用户
          // 无意义：整段不渲染，识别信息由分层行承担；股票/ETF/指数等保留 `# 代码`。
          // 判定用 asset_type 而非 advisor_platform——经理行没有 AdvisorPortfolio 记录，
          // 只认 platform 会漏掉经理（2026-09-10 用户反馈）。
          showCode: !isCompositeAsset(row)
        },
        {
          meta: () => [
            ...tagIds.slice(0, MAX_TAGS).flatMap(tagId => {
              const c = tagColor(tagId);
              // 数据色例外：标签色为用户数据（非设计令牌），缺失回退中性
              const isHex = c.startsWith("#");
              const name = tagName(tagId);
              // 标签已被删除但行上仍有残留 tag_id 时 name 为空：不渲染空 chip
              if (!name) return [];
              return [
                h(
                  "span",
                  {
                    class: ["tag-chip", { "is-clickable": editable }],
                    style: {
                      backgroundColor: isHex ? `${c}1f` : "var(--bg-soft)",
                      borderColor: isHex ? `${c}66` : "var(--border-default)"
                    },
                    title: editable ? `${name}（点击编辑标签）` : name,
                    onClick: editable ? openTagEditor : undefined,
                    onKeydown: editable
                      ? (e: KeyboardEvent) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            openTagEditor(e);
                          }
                        }
                      : undefined,
                    role: editable ? "button" : undefined,
                    tabIndex: editable ? 0 : undefined
                  },
                  name
                )
              ];
            }),
            // 超过上限的标签数：弱化小字，title 只列出「未展示」的标签名（避免与 chip 重复）
            ...(tagIds.length > MAX_TAGS
              ? [
                  h(
                    "span",
                    {
                      class: "tag-chip tag-chip--more",
                      title: tagIds
                        .slice(MAX_TAGS)
                        .map(tagName)
                        .filter(Boolean)
                        .join("、")
                    },
                    `+${tagIds.length - MAX_TAGS}`
                  )
                ]
              : []),
            // 「+ 标签」文字入口：所有真实产品行（有 symbol）均显示，hover/聚焦才显现；
            // 虚拟持仓聚合行（symbol=null）不渲染，避免无意义的入口；
            // 无 id 的真实产品行（如草稿记录）点击时由 ctx.openTagEditor 统一给出提示
            // （见 useWatchlistData.openTagEditor，避免此前 disabled 圆圈「死按钮」观感问题）。
            ...(row.symbol != null
              ? [
                  h(
                    "span",
                    {
                      class: "add-tag-btn",
                      role: "button",
                      tabIndex: 0,
                      title: "添加/编辑标签",
                      onClick: openTagEditor,
                      onKeydown: (e: KeyboardEvent) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openTagEditor(e);
                        }
                      }
                    },
                    "＋ 标签"
                  ),
                  // 「备注」入口（#1285）：**不依赖备注列是否可见**——把编辑入口内联到产品列第二行，
                  // 与「＋ 标签」同一交互语言（hover 浮现、整行有内容时提示）；已填写时以品牌色
                  // 「备注」提示「此处有内容」。避免用户必须先在列设置里开启备注列才能编辑。
                  h(
                    "span",
                    {
                      class: ["add-note-btn", { "has-note": !!noteText }],
                      role: "button",
                      tabIndex: 0,
                      title: noteText ? "编辑备注" : "添加备注",
                      onClick: openNotesEntry,
                      onKeydown: (e: KeyboardEvent) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openNotesEntry(e);
                        }
                      }
                    },
                    noteText ? "备注" : "＋ 备注"
                  )
                ]
              : [])
          ]
        }
      )
    ]
  );
};

const renderActions: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = props => {
  const row = props.row;
  const ctx = props.ctx;
  // 批量管理模式：显示 "-" 占位（对齐 index.vue 原模板）
  if (ctx.batchMode) {
    return h(
      "span",
      { class: "text-xs", style: { color: "var(--text-tertiary)" } },
      "-"
    );
  }
  const a = ctx.actions;
  // 操作列（fixed:right）三按钮：置顶 / 特别关注 / 移除。
  // 按钮**常驻弱显（45%）+ 行 hover 全亮**，见 index.vue 的 opacity 规则——
  // 显隐纯靠 CSS（行 hover 驱动 opacity），不依赖 JS hoveredRowKey；
  // hoveredRowKey 仍由本列 mouseenter/leave 写入，用于联动 product 列内
  // 置顶/加标签按钮的高亮（跨 fixed 列 DOM 无法用 :hover 同步），并非控制显隐。
  // 状态用图标颜色表达：已置顶 = 品牌色实心图钉；已关注 = 暖橙实心星。
  const editable = row.id != null;
  const tooltipBtn = (
    tip: string,
    icon: string,
    iconColor: string | undefined,
    disabled: boolean,
    onClick: (e: Event) => void
  ) =>
    h(
      ElTooltip,
      { content: tip, placement: "top" },
      {
        default: () =>
          h(
            ElButton,
            {
              circle: true,
              size: "small",
              disabled,
              onClick
            },
            () => [
              h(IconifyIconOffline, {
                icon,
                style: iconColor ? { color: iconColor } : undefined
              })
            ]
          )
      }
    );

  return h(
    "div",
    {
      class: "flex items-center justify-center gap-1",
      onMouseenter: () => ctx.setHoveredRowKey(row.id ?? row.symbol),
      onMouseleave: () => ctx.setHoveredRowKey(null)
    },
    [
      tooltipBtn(
        row.is_pinned ? "取消置顶" : "置顶",
        row.is_pinned ? "mdi:pin" : "mdi:pin-outline",
        row.is_pinned ? "var(--brand-700)" : undefined,
        !editable,
        (e: Event) => {
          e.stopPropagation();
          a.togglePin(row);
        }
      ),
      tooltipBtn(
        row.favorite ? "取消特别关注" : "特别关注",
        row.favorite ? "ep:star-filled" : "ep:star",
        row.favorite ? "var(--temp-warm)" : undefined,
        !editable,
        (e: Event) => {
          e.stopPropagation();
          a.toggleFavorite(row);
        }
      ),
      tooltipBtn(
        row.status === "HOLDING" ? "持仓资产无法直接从自选移除" : "移除",
        "ep:delete",
        undefined,
        row.status === "HOLDING" || !editable,
        (e: Event) => {
          e.stopPropagation();
          a.remove(row);
        }
      )
    ]
  );
};

/**
 * 投资笔记（#1285）：展示备注文本（或「＋ 备注」占位），点击打开编辑弹窗。
 * 与 add-tag 同语言：未填写时弱化入口，已填写时整格可点编辑；
 * 文本超长由 el-table 列的省略（title 看全文）或 CSS ellipsis 处理。
 */
const renderNotes: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = props => {
  const note = (field(props.row, "notes") as string) || "";
  const open = (e: Event) => {
    e.stopPropagation();
    props.ctx.actions.openNotesEditor(props.row);
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open(e);
    }
  };
  if (!note) {
    return h(
      "span",
      {
        class: "add-note-btn",
        role: "button",
        tabIndex: 0,
        title: "添加备注",
        onClick: open,
        onKeydown: onKey
      },
      "＋ 备注"
    );
  }
  return h(
    "span",
    {
      class: "note-cell",
      role: "button",
      tabIndex: 0,
      title: note,
      onClick: open,
      onKeydown: onKey
    },
    note
  );
};

/** renderer 类型 -> 函数式组件 的注册表 */
const REGISTRY: Record<
  ColumnRenderer,
  FunctionalComponent<{
    row: WatchlistRow;
    def: ColumnDef;
    ctx: RenderCtx;
  }>
> = {
  product: renderProduct as never,
  date: renderDate as never,
  money: renderMoney as never,
  riseFall: renderRiseFall as never,
  qty: renderQty as never,
  moneyRatio: renderMoneyRatio as never,
  text: renderText as never,
  notes: renderNotes as never,
  sparkline: renderSparkline as never,
  actions: renderActions as never
};

/** 按 renderer 类型取对应函数式组件（模板 <component :is> 用） */
export function resolveRenderer(type: ColumnRenderer) {
  return REGISTRY[type];
}

/** 渲染单个单元格（供测试或命令式调用） */
export function renderCell(
  def: ColumnDef,
  row: WatchlistRow,
  ctx: RenderCtx
): VNode {
  const Comp = resolveRenderer(def.renderer);
  return h(Comp, { row, def, ctx });
}
