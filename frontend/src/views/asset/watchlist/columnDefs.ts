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
 * 接入 v-for）与步骤 3（删除硬编码列、product/marker/actions 切 renderer）
 * 均已完成：index.vue 已切换到全量 columnDefs 驱动，仅 selection 列因
 * type="selection" 无法 renderer 化而保留模板。后续字段扩展（#990/#992/#993）
 * 均在此 columnDefs 上增量开发，不应再向 index.vue 硬编码堆列。
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
  /** #992 预留：是否参与拖拽排序（列顺序） */
  draggable?: boolean;
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
 */
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
    key: "_marker",
    label: "",
    renderer: "product", // renderer 为 product + props.builtin=marker，由 renderProduct 解析渲染置顶/关注图标
    width: 44,
    align: "center",
    fixed: "left",
    hideable: false,
    draggable: false,
    props: { builtin: "marker" }
  },
  {
    key: "product",
    label: "代码/名称",
    renderer: "product",
    minWidth: 240,
    fixed: "left",
    showOverflowTooltip: true,
    sortable: "custom",
    hideable: false,
    draggable: false
  },
  {
    key: "created_at",
    label: "添加自选日",
    renderer: "date",
    width: 130,
    align: "center",
    sortable: "custom",
    hideable: true,
    draggable: true
  },
  {
    key: "current_price",
    label: "最新价",
    renderer: "money",
    width: 110,
    align: "right",
    sortable: "custom",
    realtimeField: "currentPrice",
    hideable: true,
    draggable: true
  },
  {
    key: "change_pct",
    label: "涨跌幅",
    renderer: "riseFall",
    width: 110,
    align: "right",
    sortable: "custom",
    realtimeField: "changePct",
    hideable: true,
    draggable: true
  },
  {
    // 近 60 日收盘迷你走势（#990）：数据源 price_history，无数据降级 --
    key: "trend",
    label: "走势",
    renderer: "sparkline",
    width: 120,
    align: "center",
    hideable: true,
    draggable: true
  },
  {
    key: "holding_quantity",
    label: "持有数量",
    renderer: "qty",
    width: 130,
    align: "right",
    sortable: "custom",
    hideable: true,
    draggable: true
  },
  {
    key: "position_market_value",
    label: "持仓市值",
    renderer: "moneyRatio",
    width: 150,
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
    width: 150,
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
    width: 150,
    align: "right",
    sortable: "custom",
    hideable: true,
    draggable: true,
    // value=holding_pnl, ratio=holding_pnl_percent（renderer 内对持仓量为 0 时置 null）
    props: { ratioKey: "holding_pnl_percent" }
  },
  {
    key: "_actions",
    label: "操作",
    renderer: "actions",
    width: 120,
    align: "center",
    fixed: "right",
    hideable: false,
    draggable: false
  }
];

/**
 * 默认可见列（排除内置的 selection/marker，由模板按 batchMode/fixed 条件注入）。
 * #993 表头自定义：基于 hideable + 用户列顺序偏好（localStorage）过滤/重排得到 visibleColumns。
 * #992 拖拽排序：只改此顺序数组（持久化），不动 watchlistColumnDefs 源定义。
 */
export function getDefaultVisibleColumns(): ColumnDef[] {
  return watchlistColumnDefs.filter(
    d => d.key !== "_selection" && d.key !== "_marker"
  );
}
