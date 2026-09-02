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
 * product/marker/actions 均由本注册表渲染（selection 因 type="selection"
 * 无法 renderer 化，仍由 index.vue 模板按 batchMode 注入）。
 * 后续改 product/actions 交互只需改本文件，不再有 index.vue 模板副本。
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
  };
  /** 近 N 日收盘价序列（sparkline 列，#990）：symbol → close 数组；无数据的 symbol 键缺省 */
  trends: Record<string, number[]>;
}

/** 安全地从 row 取任意字段（WatchlistItem 无索引签名，需经 unknown 中转） */
function field(row: WatchlistRow, key: string): unknown {
  return (row as unknown as Record<string, unknown>)[key];
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
  // 迷你走势尺寸（issue #1281）：宽 64 / 高 20，贴合 design.md 行高 40–44px 基线，
  // 相比原 96×24 收窄约三分之一，在有限列宽内容纳更多数据列
  const width = 64;
  const height = 20;
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

const renderMoneyRatio: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = props => {
  const { row, def, ctx } = props;
  // 派生列（添加后涨幅 / 持仓市值比例）：直接取注入的计算结果
  if (def.derived) {
    const d = ctx.derived(def.derived, row);
    return h(MoneyWithRatio, {
      value: d.value,
      ratio: d.ratio,
      moneySize: "sm",
      // 内联单行：两行堆叠会把行高顶到 ~51px，超出 design.md 锁定的 40–44px（#1281）
      inline: true
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
    showCurrency: false,
    inline: true
  });
};

const renderProduct: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = props => {
  const row = props.row;
  const ctx = props.ctx;

  // 内置 marker 列：置顶/关注图标（对齐 index.vue 原 marker 模板）
  if (props.def.props?.builtin === "marker") {
    const markers: VNode[] = [];
    if (row.is_pinned) {
      markers.push(
        h("span", { class: "marker-icon", title: "已置顶" }, [
          h(IconifyIconOffline, { icon: "mdi:pin-outline", class: "text-sm" })
        ])
      );
    }
    if (row.favorite) {
      markers.push(
        h("span", { class: "marker-icon", title: "特别关注" }, [
          h(IconifyIconOffline, { icon: "ep:star", class: "text-sm" })
        ])
      );
    }
    return h(
      "div",
      { class: "flex items-center justify-center gap-0.5" },
      markers
    );
  }

  // 正常 product 列：单行紧凑布局 —— 名称 + 代码(+类型) + 标签圆点 + 添加标签按钮。
  // 压缩前为「名称 / 代码+类型 / 标签 chips」三行，实测行高约 78px，一屏仅 3 行；
  // 现对齐 design.md「数据表格强制紧凑原则」（自选等密集场景行高锁定 40–44px，
  // 首列名称+代码 180–220px），全部收敛到同一行，行高回落至 40px 基线，
  // 单屏可见行数翻倍（issue #1281）。
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
  /** 单行最多展示的标签圆点数，超出折叠为 +N（title 列出全部标签名） */
  const MAX_DOTS = 3;

  return h(
    "div",
    {
      class: ["product-row", { "is-row-hovered": isRowHovered }],
      onMouseenter: () => ctx.setHoveredRowKey(rowKey),
      onMouseleave: () => ctx.setHoveredRowKey(null)
    },
    [
      h(ProductDisplay, {
        compact: true,
        name: (field(row, "display_name") as string) || row.symbol,
        symbol: row.symbol,
        typeLabel: (field(row, "type_label") as string) || ""
      }),
      // 标签以 6px 圆点内联呈现：不再单独占一行、不撑高行高，
      // 标签名经 title 原生提示保留可读性（避免「仅靠颜色传意」）
      ...tagIds.slice(0, MAX_DOTS).map(tagId =>
        h("span", {
          class: "tag-dot",
          style: { backgroundColor: tagColor(tagId) },
          title: tagName(tagId)
        })
      ),
      ...(tagIds.length > MAX_DOTS
        ? [
            h(
              "span",
              {
                class: "tag-dot-more",
                title: tagIds
                  .slice(MAX_DOTS)
                  .map(tagName)
                  .filter(Boolean)
                  .join("、")
              },
              `+${tagIds.length - MAX_DOTS}`
            )
          ]
        : []),
      h(
        ElTooltip,
        { content: "添加/编辑标签", placement: "top" },
        {
          default: () =>
            h(
              ElButton,
              {
                circle: true,
                size: "small",
                class: "add-tag-btn",
                disabled: row.id == null,
                onClick: (e: Event) => {
                  e.stopPropagation();
                  ctx.openTagEditor(row);
                }
              },
              () => [
                h(IconifyIconOffline, {
                  icon: "ep:plus",
                  class: "text-[10px]"
                })
              ]
            )
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
  // 操作列是 fixed:right 列（EP 固定列独立 DOM），行 hover 淡入由 JS 状态（hoveredRowKey）驱动；
  // 容器自身绑定 mouseenter/leave 自驱动，鼠标直接悬停固定列时也能亮起按钮
  const isRowHovered =
    ctx.hoveredRowKey != null && ctx.hoveredRowKey === (row.id ?? row.symbol);
  const rowKey = row.id ?? row.symbol;
  return h(
    "div",
    {
      class: [
        "flex items-center justify-center gap-1",
        { "is-row-hovered": isRowHovered }
      ],
      onMouseenter: () => ctx.setHoveredRowKey(rowKey),
      onMouseleave: () => ctx.setHoveredRowKey(null)
    },
    [
      h(
        ElTooltip,
        { content: row.is_pinned ? "取消置顶" : "置顶", placement: "top" },
        {
          default: () =>
            h(
              ElButton,
              {
                circle: true,
                size: "small",
                disabled: row.id == null,
                onClick: (e: Event) => {
                  e.stopPropagation();
                  a.togglePin(row);
                }
              },
              () => [
                h(IconifyIconOffline, {
                  icon: row.is_pinned ? "mdi:pin" : "mdi:pin-outline"
                })
              ]
            )
        }
      ),
      h(
        ElTooltip,
        {
          content: row.favorite ? "取消特别关注" : "特别关注",
          placement: "top"
        },
        {
          default: () =>
            h(
              ElButton,
              {
                circle: true,
                size: "small",
                disabled: row.id == null,
                onClick: (e: Event) => {
                  e.stopPropagation();
                  a.toggleFavorite(row);
                }
              },
              () => [
                h(IconifyIconOffline, {
                  icon: row.favorite ? "ep:star-filled" : "ep:star"
                })
              ]
            )
        }
      ),
      h(
        ElTooltip,
        {
          content:
            row.status === "HOLDING" ? "持仓资产无法直接从自选移除" : "移除",
          placement: "top"
        },
        {
          default: () =>
            h(
              ElButton,
              {
                circle: true,
                size: "small",
                class: "btn-delete-ghost",
                disabled: row.status === "HOLDING",
                onClick: (e: Event) => {
                  e.stopPropagation();
                  a.remove(row);
                }
              },
              () => [h(IconifyIconOffline, { icon: "ep:delete" })]
            )
        }
      )
    ]
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
