// 未竟之蹊（/the-road-not-taken）页面常量：胶囊维度、类型色、排序与示例卡。
//
// 设计基线：docs/features/watchlist.md §1.5.7「未竟之蹊」+ frontend/design.md
// 「Filter & Selection」（两级胶囊：一级主维度 / 二级状态维度，禁止左侧边栏）。
// 编码红线：本文件只出现设计令牌与用户数据色；涨跌一律走 --color-rise / --color-fall。

import type {
  RoadEntityType,
  RoadHoldingState,
  RoadItem,
  RoadStatusFilter
} from "@/types/favorites";

/** 一级胶囊：标的类别（主维度） */
export interface EntityTab {
  key: RoadEntityType | "all";
  label: string;
}

export const ENTITY_TABS: EntityTab[] = [
  { key: "all", label: "全部" },
  { key: "stock", label: "股票" },
  { key: "fund", label: "基金" },
  { key: "manager", label: "经理" },
  { key: "index", label: "指数" }
];

/** 二级胶囊：状态（子维度，含「待复盘」虚拟筛选） */
export interface StatusTab {
  key: RoadStatusFilter;
  label: string;
}

export const STATUS_TABS: StatusTab[] = [
  { key: "all", label: "全部状态" },
  { key: "review", label: "待复盘" },
  { key: "holding", label: "持仓中" },
  { key: "watching", label: "观察中" },
  { key: "cleared", label: "已清仓" }
];

/**
 * 类型色（封面主色）：复用资产类型语义令牌，缺失回退中性色。
 * cover 只用于封面色层，卡片文字/边框仍走语义令牌。
 */
export const ENTITY_COLOR: Record<RoadEntityType, string> = {
  stock: "var(--asset-stock)",
  fund: "var(--asset-fund)",
  index: "var(--tag-warm-sand)",
  manager: "var(--tag-purple-gray)"
};

export const ENTITY_LABEL: Record<RoadEntityType, string> = {
  stock: "股票",
  fund: "基金",
  index: "指数",
  manager: "经理"
};

export const HOLDING_STATE_LABEL: Record<RoadHoldingState, string> = {
  holding: "持仓中",
  watching: "观察中",
  cleared: "已清仓"
};

export const VENUE_LABEL: Record<string, string> = {
  EXCHANGE: "场内",
  OTC: "场外"
};

/**
 * 资产类型 → 一级胶囊归类（ETF/可转债归入股票，与其交易属性一致）。
 * 输入大小写归一为小写后再判断，与后端 asset_types 单一来源（stock/etf/fund/bond/index）保持一致（#1171）。
 * 注意：卡片上的中文标签不再在此手抄，统一走 useEnumLabels.assetTypeLabel（后端 /enums 单一来源，回退前端镜像）。
 */
export function toEntityType(
  assetType: string | null | undefined
): RoadEntityType {
  switch ((assetType || "").toLowerCase()) {
    case "fund":
      return "fund";
    case "index":
      return "index";
    case "etf":
    case "cb":
    case "stock":
    default:
      return "stock";
  }
}

/** 排序选项（非筛选维度，故不占胶囊位） */
export const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "updated_at", label: "最近更新" },
  { value: "favorite_at", label: "标记时间" },
  { value: "next_review_date", label: "复盘日期" }
];

export const PAGE_SIZE = 12;

/** 迷你走势取数天数（与后端 trends 接口 days 参数一致） */
export const TREND_DAYS = 120;

// ─────────────── 设计预览示例卡（非真实数据） ───────────────
// 用途：基金经理追踪等能力后端尚未落地时，用于呈现完整设计（AGENTS.md：
// 禁止把编造数值混进真实数据，故示例卡常驻 isDemo 标记且不可保存）。

/** 由种子生成确定性走势序列，避免每次渲染跳动 */
function demoTrend(seed: number, points = 40): number[] {
  const out: number[] = [];
  let value = 100;
  for (let i = 0; i < points; i += 1) {
    const wave =
      Math.sin((i + seed) / 4) * 2.4 + Math.cos((i + seed) / 9) * 1.6;
    value = Math.max(60, value + wave + (seed % 5) * 0.12 - 0.2);
    out.push(Number(value.toFixed(2)));
  }
  return out;
}

const DAY = 24 * 60 * 60 * 1000;
const iso = (offsetDays: number) =>
  new Date(Date.now() + offsetDays * DAY).toISOString().slice(0, 10);

// 类型/状态/笔记长度/是否有走势与指标全方位错位，用于验证瀑布流是否真正不等高
// （并非「一种卡片、等高」）。注意：全部为 isDemo 占位，禁止保存、数值均为演示种子。
export const DEMO_ITEMS: RoadItem[] = [
  {
    id: null,
    symbol: "OF.110022",
    market: "OF",
    display_name: "易方达消费行业股票",
    asset_type: "fund",
    venue: "OTC",
    entity: "fund",
    holdingState: "watching",
    favorite_at: iso(-126),
    next_review_date: iso(9),
    is_pinned: true,
    notes:
      "消费复苏节奏低于预期，暂不加仓；等中报披露后再决定是否补仓，同时观察白酒批价与动销的边际变化。",
    notes_summary:
      "消费复苏节奏低于预期，暂不加仓；等中报披露后再决定是否补仓，同时观察白酒批价与动销的边际变化。",
    add_reason: "长期跟踪消费赛道",
    tag_ids: [],
    trend: demoTrend(3),
    current_price: 3.182,
    price_at_added: 3.641,
    holding_quantity: null,
    holding_pnl: null,
    holding_pnl_percent: null,
    position_market_value: 0,
    created_at: iso(-420),
    updated_at: iso(-6),
    isDemo: true
  },
  {
    id: null,
    symbol: "MGR.ZHANGKUN",
    market: "MGR",
    display_name: "张坤",
    asset_type: "manager",
    venue: null,
    entity: "manager",
    holdingState: "watching",
    favorite_at: iso(-58),
    next_review_date: iso(21),
    is_pinned: false,
    notes:
      "看他从易方达中小盘到蓝筹精选的风格迁移，重点观察回撤控制与仓位集中度。",
    notes_summary:
      "看他从易方达中小盘到蓝筹精选的风格迁移，重点观察回撤控制与仓位集中度。",
    add_reason: "跟踪经理生涯",
    tag_ids: [],
    trend: demoTrend(7),
    current_price: null,
    price_at_added: null,
    holding_quantity: null,
    holding_pnl: null,
    holding_pnl_percent: null,
    position_market_value: 0,
    created_at: iso(-300),
    updated_at: iso(-2),
    isDemo: true
  },
  {
    id: null,
    symbol: "SH.600519",
    market: "SH",
    display_name: "贵州茅台",
    asset_type: "stock",
    venue: "EXCHANGE",
    entity: "stock",
    holdingState: "cleared",
    favorite_at: iso(-534),
    next_review_date: iso(-3),
    is_pinned: false,
    notes: "估值回到合理区间但消费不及预期，先清仓观察，等旺季动销数据。",
    notes_summary:
      "估值回到合理区间但消费不及预期，先清仓观察，等旺季动销数据。",
    add_reason: "核心资产",
    tag_ids: [],
    trend: demoTrend(11),
    current_price: 1428.6,
    price_at_added: 1652.0,
    holding_quantity: null,
    holding_pnl: null,
    holding_pnl_percent: null,
    position_market_value: 0,
    created_at: iso(-900),
    updated_at: iso(-3),
    isDemo: true
  },
  {
    id: null,
    symbol: "SZ.399997",
    market: "SZ",
    display_name: "中证白酒指数",
    asset_type: "index",
    venue: null,
    entity: "index",
    holdingState: "watching",
    favorite_at: iso(-88),
    next_review_date: iso(45),
    is_pinned: false,
    notes: "作为消费仓位的基准参照，先看估值分位再谈加仓。",
    notes_summary: "作为消费仓位的基准参照，先看估值分位再谈加仓。",
    add_reason: "基准参照",
    tag_ids: [],
    trend: demoTrend(17),
    current_price: 12463.2,
    price_at_added: 13880.5,
    holding_quantity: null,
    holding_pnl: null,
    holding_pnl_percent: null,
    position_market_value: 0,
    created_at: iso(-260),
    updated_at: iso(-1),
    isDemo: true
  },
  {
    id: null,
    symbol: "OF.003095",
    market: "OF",
    display_name: "中欧医疗健康混合A",
    asset_type: "fund",
    venue: "OTC",
    entity: "fund",
    holdingState: "holding",
    favorite_at: iso(-310),
    next_review_date: iso(14),
    is_pinned: false,
    notes:
      "医疗集采靴子陆续落地，估值进入历史低位，定投摊薄成本，但短期政策扰动仍大，不急于一把梭。",
    notes_summary:
      "医疗集采靴子陆续落地，估值进入历史低位，定投摊薄成本，但短期政策扰动仍大，不急于一把梭。",
    add_reason: "长坡厚雪",
    tag_ids: [],
    trend: demoTrend(5),
    current_price: 2.014,
    price_at_added: 2.195,
    holding_quantity: 1200,
    holding_pnl: -386.4,
    holding_pnl_percent: -8.21,
    position_market_value: 2416.8,
    created_at: iso(-310),
    updated_at: iso(-4),
    isDemo: true
  },
  {
    // 无行情、无走势：验证「行情数据积累中」占位 + 矮卡
    id: null,
    symbol: "OF.161725",
    market: "OF",
    display_name: "招商中证白酒指数(LOF)",
    asset_type: "fund",
    venue: "OTC",
    entity: "fund",
    holdingState: "watching",
    favorite_at: iso(-40),
    next_review_date: null,
    is_pinned: false,
    notes: "白酒仓位的对标工具，等周线级别企稳信号再建仓。",
    notes_summary: "白酒仓位的对标工具，等周线级别企稳信号再建仓。",
    add_reason: "对标工具",
    tag_ids: [],
    trend: [],
    current_price: null,
    price_at_added: null,
    holding_quantity: null,
    holding_pnl: null,
    holding_pnl_percent: null,
    position_market_value: 0,
    created_at: iso(-40),
    updated_at: iso(-40),
    isDemo: true
  },
  {
    id: null,
    symbol: "SZ.300750",
    market: "SZ",
    display_name: "宁德时代",
    asset_type: "stock",
    venue: "EXCHANGE",
    entity: "stock",
    holdingState: "holding",
    favorite_at: iso(-200),
    next_review_date: iso(30),
    is_pinned: true,
    notes: "储能与海外占比提升，估值消化较充分。",
    notes_summary: "储能与海外占比提升，估值消化较充分。",
    add_reason: "新能源龙头",
    tag_ids: [],
    trend: demoTrend(13),
    current_price: 248.3,
    price_at_added: 233.1,
    holding_quantity: 100,
    holding_pnl: 1230.5,
    holding_pnl_percent: 6.4,
    position_market_value: 24830.0,
    created_at: iso(-200),
    updated_at: iso(-5),
    isDemo: true
  },
  {
    id: null,
    symbol: "SH.000300",
    market: "SH",
    display_name: "沪深300",
    asset_type: "index",
    venue: null,
    entity: "index",
    holdingState: "watching",
    favorite_at: iso(-15),
    next_review_date: iso(60),
    is_pinned: false,
    notes: "宽基底仓的锚，不看个股时用来校准整体仓位。",
    notes_summary: "宽基底仓的锚，不看个股时用来校准整体仓位。",
    add_reason: "基准",
    tag_ids: [],
    trend: demoTrend(21),
    current_price: 3892.1,
    price_at_added: 4011.7,
    holding_quantity: null,
    holding_pnl: null,
    holding_pnl_percent: null,
    position_market_value: 0,
    created_at: iso(-15),
    updated_at: iso(-1),
    isDemo: true
  },
  {
    id: null,
    symbol: "MGR.GELAN",
    market: "MGR",
    display_name: "葛兰",
    asset_type: "manager",
    venue: null,
    entity: "manager",
    holdingState: "watching",
    favorite_at: iso(-72),
    next_review_date: iso(18),
    is_pinned: false,
    notes: "医药主题基金经理，波动大，观察其回撤与择时能力再决定是否跟投。",
    notes_summary:
      "医药主题基金经理，波动大，观察其回撤与择时能力再决定是否跟投。",
    add_reason: "跟踪经理",
    tag_ids: [],
    trend: demoTrend(9),
    current_price: null,
    price_at_added: null,
    holding_quantity: null,
    holding_pnl: null,
    holding_pnl_percent: null,
    position_market_value: 0,
    created_at: iso(-72),
    updated_at: iso(-2),
    isDemo: true
  },
  {
    // 无笔记：验证「还没写下第一段思考。」占位的矮卡
    id: null,
    symbol: "OF.005827",
    market: "OF",
    display_name: "易方达蓝筹精选混合",
    asset_type: "fund",
    venue: "OTC",
    entity: "fund",
    holdingState: "watching",
    favorite_at: iso(-96),
    next_review_date: iso(20),
    is_pinned: false,
    notes: null,
    notes_summary: null,
    add_reason: "蓝筹精选",
    tag_ids: [],
    trend: demoTrend(2),
    current_price: 2.41,
    price_at_added: 2.88,
    holding_quantity: null,
    holding_pnl: null,
    holding_pnl_percent: null,
    position_market_value: 0,
    created_at: iso(-96),
    updated_at: iso(-7),
    isDemo: true
  },
  {
    // 已清仓 + 无笔记 + 复盘逾期：验证逾期红色提醒与矮卡并存
    id: null,
    symbol: "SZ.002594",
    market: "SZ",
    display_name: "比亚迪",
    asset_type: "stock",
    venue: "EXCHANGE",
    entity: "stock",
    holdingState: "cleared",
    favorite_at: iso(-420),
    next_review_date: iso(-5),
    is_pinned: false,
    notes: null,
    notes_summary: null,
    add_reason: "新能源车",
    tag_ids: [],
    trend: demoTrend(15),
    current_price: 265.0,
    price_at_added: 312.4,
    holding_quantity: null,
    holding_pnl: null,
    holding_pnl_percent: null,
    position_market_value: 0,
    created_at: iso(-420),
    updated_at: iso(-5),
    isDemo: true
  },
  {
    id: null,
    symbol: "SH.511010",
    market: "SH",
    display_name: "国债ETF",
    asset_type: "etf",
    venue: "EXCHANGE",
    entity: "stock",
    holdingState: "holding",
    favorite_at: iso(-150),
    next_review_date: iso(90),
    is_pinned: false,
    notes: "组合压舱石，和权益负相关，用来对冲尾部风险。",
    notes_summary: "组合压舱石，和权益负相关，用来对冲尾部风险。",
    add_reason: "避险",
    tag_ids: [],
    trend: demoTrend(25),
    current_price: 112.3,
    price_at_added: 110.1,
    holding_quantity: 500,
    holding_pnl: 89.2,
    holding_pnl_percent: 1.8,
    position_market_value: 56150.0,
    created_at: iso(-150),
    updated_at: iso(-8),
    isDemo: true
  }
];
