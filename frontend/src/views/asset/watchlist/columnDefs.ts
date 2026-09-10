/**
 * watchlist 自选表格列定义（columnDefs，数据驱动）
 *
 * 对应 issue #995（umbrella #1022）。
 * 把 index.vue 中 21 个硬编码 <el-table-column> 抽象为可配置的数据结构，
 * 模板改为 v-for 渲染。新增字段只改本文件 + renderer 注册表，不碰大组件。
 *
 * 实时数据继续走 useRealtimeQuotes（getValuationItem），renderer 内部
 * 内聚「实时覆盖静态」的双分支逻辑（见 columnRenderers.tsx），
 * 不在模板里散落 v-if realtimeEnabled。
 *
 * 约束（AGENTS.md）：不得在本文件/renderer 内新开 JSONP 通道；
 * 新实时字段一律经实时数据链路 renderer 消费。
 *
 * ── 实施状态（维护者须知）──
 * MVP 步骤 1（本文件 + columnRenderers.tsx 落地）、步骤 2（index.vue 数据列
 * 接入 v-for）与步骤 3（删除硬编码列、product/actions 切 renderer）
 * 均已完成：index.vue 已切换到全量 columnDefs 驱动，仅 selection 列因
 * type="selection" 无法 renderer 化而保留模板。后续字段扩展（#990/#992/#993）
 * 均在此 columnDefs 上增量开发，不应再向 index.vue 硬编码堆列。
 *
 * ── 2026-09-04 密度优化（#1281 第四轮）──
 * 原独立 marker 列（44px，置顶/关注状态图标）已删除：状态标记改为内联到
 * product 列名称前（常驻可见、点击即切换，见 columnRenderers.tsx renderProduct），
 * 置顶行另由 index.vue 的 :row-class-name 加底色区分；本表因此净释放约 44px
 * 横向空间（原独立 marker 列 44px 已并入 product 列内联，actions 列宽保持 110）。
 */

import type { WatchlistItem } from "@/api/watchlist";

export type WatchlistRow = WatchlistItem;

/** 单元格渲染器类型，对应 columnRenderers.tsx 中的注册表 */
export type ColumnRenderer =
  | "product" // 代码/名称 + 标签 chips（ProductDisplay + TagChips）
  | "date" // 格式化日期（formatDate）
  | "money" // MoneyDisplay（精度按 asset_type）
  | "riseFall" // RiseFallText（涨跌幅，支持实时覆盖）
  | "qty" // 持有数量 + 单位（份/股）
  | "moneyRatio" // MoneyWithRatio（金额 + 比率）
  | "sparkline" // 迷你走势图（纯 SVG 折线，#990）
  | "text" // 纯文本 / 枚举映射（#993 新增列：资产类型、所属分组）
  | "notes" // 投资笔记（点击编辑，#1285）
  | "bond" // 可转债条款（#1285/#1393：溢价率 / 强赎状态 / 剩余年限 / 评级）
  | "indexVal" // 指数估值（#1285/#1394：市盈率 / 股息率，中证官方）
  | "actions"; // 操作列（circle 按钮：置顶/关注/编辑/删除）

/** 实时估值可覆盖的字段（来自 getValuationItem 产出） */
export type RealtimeField = "currentPrice" | "changePct";

export interface ColumnDef {
  /** 唯一键，如 "current_price"；以 _ 开头为内置/非数据列（selection/marker/actions） */
  key: string;
  /** 表头文案 */
  label: string;
  /** 渲染器类型 */
  renderer: ColumnRenderer;
  width?: number;
  minWidth?: number;
  align?: "left" | "center" | "right";
  fixed?: "left" | "right";
  /** 排序模式：固定 "custom"（#991 后端排序透传，EP 不做页内排序） */
  sortable?: "custom";
  /** 开启实时且存在估值项时，用估值项的该字段覆盖静态值 */
  realtimeField?: RealtimeField;
  /** #993 预留：用户是否可隐藏 */
  hideable?: boolean;
  /**
   * #993 新增列：默认隐藏（仅记录在「管理 → 列设置」中被显式开启的列）。
   * 为什么需要它：持久化只存「被隐藏的 key」，若新列默认可见，每次增列都会
   * 直接加宽表格、冲击 #1281 换来的单屏行数。改为默认隐藏后，新列是「可选能力」
   * 而非「默认负担」，老用户升级也不会被旧缓存吃掉新列。
   */
  defaultHidden?: boolean;
  /** #992 预留：是否参与拖拽排序（列顺序） */
  draggable?: boolean;
  /**
   * 视图作用域（#1285 品类差异化）：
   * - `"mixed"`：混合视图（未按品类筛选）也显示的「通用列」——名称 / 价格净值 / 涨跌幅 / 操作。
   * - `"category"`（默认）：仅在「品类视图」（类型筛选命中单一品类）显示；
   *   用户若在「列设置」显式开启，则任何视图都显示（当前标的不适用时渲染 `—`）。
   */
  scope?: "mixed" | "category";
  /**
   * 适用的资产类型（`asset_type` 小写枚举）；缺省 = 全部类型。
   * 仅对 `scope="category"` 生效：品类视图下只展示命中品类的列
   * （如持仓 / 市值类列只对可交易标的，指数 / 经理 / 组合不出现）。
   */
  appliesTo?: string[];
  /** 名称超长时省略并 hover 显示完整内容（对应 el-table-column show-overflow-tooltip） */
  showOverflowTooltip?: boolean;
  /** 渲染器所需额外参数 */
  props?: Record<string, unknown>;
  /**
   * 派生值来源（非 row 直接字段，由 index.vue 注入计算函数）。
   * 如「添加后涨幅」「持仓市值比例」是组合计算，renderer 经 ctx.derived 取。
   */
  derived?: "addedReturn" | "marketValue";
}

/**
 * 自选表格列定义清单（首批，从 index.vue 现有 21 列映射）。
 * 顺序即默认展示顺序；#992 拖拽只改 visibleColumns 顺序数组，不动本源。
 *
 * 新增列会增加表格总宽：页面级横向溢出已由 index.vue 的 flex min-width:0 链兜底
 * （超出视口的部分在 el-table 内部横向滚动，不撑宽页面，见 #1341），故此处无需为
 * 防溢出刻意压窄列宽——保持各列可读性即可。
 */
/**
 * 可交易 / 可持有资产类型：持仓数量、市值、涨跌收益等列**仅对它们有意义**。
 * 指数（不可买）、基金经理、投顾组合（非交易实体）不在此列，品类视图下不展示这些列。
 */
export const TRADABLE_TYPES = [
  "stock",
  "etf",
  "fund",
  "money_fund",
  "bond",
  "crypto",
  "reverse_repo"
];

export const watchlistColumnDefs: ColumnDef[] = [
  {
    key: "_selection",
    label: "",
    renderer: "product", // type=selection 无法 renderer 化，仍由 index.vue 模板按 batchMode 注入，本 def 仅作占位/排除项
    width: 48,
    align: "center",
    hideable: false,
    draggable: false,
    props: { builtin: "selection" }
  },
  {
    key: "product",
    label: "代码/名称",
    renderer: "product",
    // design.md「冻结列与横向滚动规范」+ components.md「ProductDisplay 列宽三档」：
    // 自选属「含类型标签且列多需要呼吸感」档，首列 232px 并左侧冻结。
    // 注意：不能用 show-overflow-tooltip——EP 会给单元格加 white-space:nowrap，
    // 会把「名称 / 代码+标签」的两行结构压回一行（#1281 单行压扁式的成因之一）；
    // 长名称由 ProductDisplay 内部 ellipsis + title 全名兜底。
    width: 232,
    fixed: "left",
    sortable: "custom",
    hideable: false,
    draggable: false,
    scope: "mixed"
  },
  {
    key: "created_at",
    label: "添加自选日",
    renderer: "date",
    width: 112,
    align: "center",
    sortable: "custom",
    hideable: true,
    draggable: true
  },
  {
    key: "current_price",
    label: "最新价",
    renderer: "money",
    width: 96,
    align: "right",
    sortable: "custom",
    realtimeField: "currentPrice",
    scope: "mixed",
    hideable: true,
    draggable: true
  },
  {
    key: "change_pct",
    label: "涨跌幅",
    renderer: "riseFall",
    width: 96,
    align: "right",
    sortable: "custom",
    realtimeField: "changePct",
    scope: "mixed",
    hideable: true,
    draggable: true
  },
  // ── 可转债品类专属列（#1285 消费侧 / #1393）──
  // 决策核心是「条款博弈」：强赎状态优先于行情，故紧随涨跌幅之后。
  // scope 缺省 = "category"：仅「可转债」品类视图显示；appliesTo=["bond"] 保证其他
  // 品类视图不出现。数据来自后端 convertible_bond_terms enrich（未落库时渲染 `—`）。
  // 不加 sortable：后端排序白名单暂未登记 bond_* 字段。
  {
    key: "bond_premium_rate",
    label: "转股溢价率",
    renderer: "bond",
    appliesTo: ["bond"],
    width: 104,
    align: "right",
    hideable: true,
    draggable: true
  },
  {
    // 复合列：强赎状态 + 天计数（如「已满足强赎条件 3/15」），完整文案在 title
    key: "bond_redeem",
    label: "强赎状态",
    renderer: "bond",
    appliesTo: ["bond"],
    width: 148,
    align: "left",
    hideable: true,
    draggable: true
  },
  {
    // 由 bond_maturity_date 现算（不新增后端字段），title 显示到期日
    key: "bond_remain_years",
    label: "剩余年限",
    renderer: "bond",
    appliesTo: ["bond"],
    width: 96,
    align: "right",
    hideable: true,
    draggable: true
  },
  {
    key: "bond_rating",
    label: "评级",
    renderer: "bond",
    appliesTo: ["bond"],
    width: 84,
    align: "center",
    hideable: true,
    draggable: true
  },
  // ── 指数品类专属列（#1285 消费侧「指数」/ #1394）──
  // 来源中证指数官方估值文件（免 cookie）。官方只下发近约 20 个交易日，
  // 故「历史分位」暂不提供（见 #1394 讨论）；估值日期挂在 title 上，口径透明。
  {
    key: "index_pe",
    label: "市盈率",
    renderer: "indexVal",
    appliesTo: ["index"],
    width: 88,
    align: "right",
    hideable: true,
    draggable: true
  },
  {
    key: "index_dividend_yield",
    label: "股息率",
    renderer: "indexVal",
    appliesTo: ["index"],
    width: 88,
    align: "right",
    hideable: true,
    draggable: true
  },
  {
    // 近 60 日收盘迷你走势（#990）：数据源 price_history，无数据降级 --
    key: "trend",
    label: "走势",
    renderer: "sparkline",
    appliesTo: TRADABLE_TYPES,
    // 图形 72×22（#1281 第二轮：20px 高在 54px 行高里显得过扁，回调到 22px）+
    // 左右各 10px 留白 = 92px 列宽
    width: 92,
    align: "center",
    hideable: true,
    draggable: true
  },
  {
    key: "holding_quantity",
    label: "持有数量",
    renderer: "qty",
    appliesTo: TRADABLE_TYPES,
    width: 112,
    align: "right",
    sortable: "custom",
    hideable: true,
    draggable: true
  },
  {
    key: "position_market_value",
    label: "持仓市值",
    renderer: "moneyRatio",
    appliesTo: TRADABLE_TYPES,
    // 两行堆叠（金额在上、占比在下）：列宽只需容纳 `¥109,600.00`（约 96px）
    // + 单元格左右 padding，148px 留有余量
    width: 148,
    align: "right",
    sortable: "custom",
    hideable: true,
    draggable: true,
    derived: "marketValue" // value=position_market_value, ratio=marketValueRatio(row)
  },
  {
    key: "added_return",
    label: "添加后涨幅",
    renderer: "moneyRatio",
    appliesTo: TRADABLE_TYPES,
    // 同持仓市值：两行堆叠，148px
    width: 148,
    align: "right",
    sortable: "custom",
    hideable: true,
    draggable: true,
    derived: "addedReturn" // value=addedReturnAmount(row), ratio=addedReturnPct(row)
  },
  {
    key: "holding_pnl",
    label: "持仓收益",
    renderer: "moneyRatio",
    appliesTo: TRADABLE_TYPES,
    // 无货币符号（showCurrency=false），宽度需求小于另两个金额列
    width: 136,
    align: "right",
    sortable: "custom",
    hideable: true,
    draggable: true,
    // value=holding_pnl, ratio=holding_pnl_percent（renderer 内对持仓量为 0 时置 null）
    props: { ratioKey: "holding_pnl_percent" }
  },

  // ── #993(a) 新增候选列 ──
  // 数据全部来自后端既有字段或前端可派生，不改动后端接口契约（符合 #993 范围边界）。
  // 均带 defaultHidden：新列是「可选能力」而非「默认负担」，避免加宽表格
  // 冲击 #1281 换来的单屏行数；用户在「管理 → 列设置」中勾选后才展示。
  // 排序（#1332）：后端 _USER_SORTABLE_FIELDS 已放开 holding_cost_price/type_label/
  // updated_at/groups，故下方四列均标 sortable:"custom"（排序透传后端，#991 同款）；
  // groups 为多值字段，排序语义取首个分组（group_ids 首个，字典序），见后端 _user_sort_metric。
  {
    // 加权成本均价（后端 holding_cost_price，positions 表汇总）
    key: "holding_cost_price",
    label: "成本价",
    renderer: "money",
    appliesTo: TRADABLE_TYPES,
    // #1332：开放列内排序（白名单已登记）；无真实持仓时显示 --
    sortable: "custom",
    props: { nullable: true },
    width: 96,
    align: "right",
    hideable: true,
    draggable: true,
    defaultHidden: true
  },
  {
    // 资产类型中文标签（后端动态字段 type_label）
    key: "type_label",
    label: "资产类型",
    renderer: "text",
    // #1332：开放列内排序（白名单已登记 type_label）
    sortable: "custom",
    width: 104,
    align: "center",
    hideable: true,
    draggable: true,
    defaultHidden: true
  },
  {
    // 所属分组：group_ids → 分组名（id→名称映射由 ctx.groupNames 注入 index.vue）
    // #1332：多值字段排序语义——按首个分组（group_ids 首个，字典序），见后端 _user_sort_metric
    key: "groups",
    label: "所属分组",
    renderer: "text",
    // #1332：开放列内排序（白名单已登记 groups，后端按 group_names 首个名排）
    sortable: "custom",
    width: 132,
    align: "left",
    hideable: true,
    draggable: true,
    defaultHidden: true
  },
  {
    key: "updated_at",
    label: "更新时间",
    renderer: "date",
    width: 112,
    align: "center",
    sortable: "custom", // #1332：后端排序白名单已放开 updated_at（ISO 字符串字典序即时间序）
    hideable: true,
    draggable: true,
    defaultHidden: true
  },
  {
    // 备注编辑（#1285）。必须 defaultHidden:true —— 遵循本文件 #993 约定「新列默认隐藏」：
    // 新列若默认可见，会直接加宽表格、顶出横向滚动条（#1381 曾误设 false 而复现该回归）。
    // 用户经「管理 → 列设置」显式开启；编辑入口见列 renderer（点击整格打开 NotesEditorDialog）。
    key: "notes",
    label: "备注",
    renderer: "notes",
    width: 180,
    align: "left",
    hideable: true,
    draggable: true,
    defaultHidden: true
  },
  {
    // 操作列：置顶 / 特别关注 / 移除 三个按钮，默认 45% 弱显、行 hover 全亮
    //（2026-09-05 回归）：曾把按钮拆到产品列 hover 图标，但 fixed 列 hover 状态
    // 在 EP 中不稳定，出现「有的行 hover 不出现」——回到固定的右固定操作列，
    // 状态以按钮图标颜色表达（置顶品牌色 / 关注暖橙），不依赖 JS hover 同步。
    key: "_actions",
    label: "操作",
    renderer: "actions",
    width: 110,
    align: "center",
    fixed: "right",
    scope: "mixed",
    hideable: false,
    draggable: false
  }
];

/**
 * 默认可见列（排除内置 selection——它由模板按 batchMode 条件注入）。
 * 原独立 marker（置顶/关注状态列）已删除：状态改为 product 列内联 + 置顶行底色，
 * 故 defs 中仅保留 selection 与 actions 两个内置列，不再有 marker。
 * #993 表头自定义：基于 hideable + 用户列顺序偏好（localStorage）过滤/重排得到 visibleColumns。
 * #992 拖拽排序：只改此顺序数组（持久化），不动 watchlistColumnDefs 源定义。
 */
export function getDefaultVisibleColumns(): ColumnDef[] {
  return watchlistColumnDefs.filter(d => d.key !== "_selection");
}
