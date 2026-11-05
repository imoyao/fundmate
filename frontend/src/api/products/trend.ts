// frontend/src/api/products/trend.ts
// 关联标的 / 走势 K 线 / 交易时间线（#2878 子域拆分；实现逐字搬自 api/products.ts，端点契约勿改）
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 跨渠道关联标的条目（`/api/products/related-symbols/` 返回） */
export interface RelatedSymbolLink {
  /** 关联标的**裸代码**（关系表统一存裸代码，无市场前缀） */
  code: string;
  /** 名称；缺失时为 null，前端降级显示代码 */
  name: string | null;
  /** 关系类型：index_etf（指数↔场内ETF）/ etf_feeder（场内ETF↔场外联接） */
  link_type: "index_etf" | "etf_feeder";
  /** 按本标的角色决定的称呼，如「同标的 ETF」「跟踪指数」「场外联接」 */
  label: string;
  /**
   * **对端**在本条关系中的角色（#1974）：`index` 指数 / `etf` 场内 ETF /
   * `feeder` 场外联接基金。前端按它决定跳 `/index/` `/etf/` 还是 `/fund/`。
   *
   * 为什么必须后端给：同一条 `index_etf` 关系，站在指数侧看到的是 ETF、站在 ETF 侧
   * 看到的是指数——前端只看 `label` 文案反推等于拿给人看的文案当数据用。
   */
  peer_role: "index" | "etf" | "feeder";
}

/** 关联标的聚合结果（#1976）。links 为空即无关联，前端降级「—」，不是错误。 */
export interface RelatedSymbolsResult {
  links: RelatedSymbolLink[];
  /** 按出现顺序去重的分组标签，用于分区展示 */
  groups: string[];
}

/**
 * 跨渠道关联标的（指数 ↔ 场内 ETF ↔ 场外联接）。
 *
 * 关系靠名称匹配建立，落库口径覆盖率约 66.4%（跨境 / 商品 ETF 缺口见 #1419），
 * 故**无关联是正常情形**，后端返回空列表而非 404。
 */
export function getRelatedSymbols(params: { symbol: string }) {
  return http.request<ApiResponse<RelatedSymbolsResult>>(
    "get",
    "/api/products/related-symbols/",
    { params }
  );
}

/** 场内单根 K 线（#1969） */
export interface ProductTrendOhlc {
  date: string;
  /** 盘中价可能为 null（存量行缺列）；前端绘制时退化为收盘价，不留空洞 */
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

/** 走势区间档位（设计 §5 B 区块；默认 3M 见 §12 ⑤） */
export type TrendRange = "1M" | "3M" | "6M" | "1Y" | "3Y" | "5Y";

export interface ProductTrendResult {
  symbol: string;
  /** `close`=场内收盘价口径；`nav`=场外累计净值（缺失回退单位净值，#2171）；空串=该品类无序列数据源（指数等） */
  kind: string;
  /** 与 values 等长的日期轴（YYYY-MM-DD） */
  dates: string[];
  values: number[];
  /** 数据来源**站点名**（如「新浪财经」「天天基金」）；#1969 前这里回的是内部表名 */
  source: string;
  /** 口径说明（如「前复权收盘价」「累计净值」）——与来源分开表达，前端不自行推断 */
  basis: string;
  range: TrendRange;
  /** 请求的区间天数（3M → 90） */
  requested_days: number;
  /** 实际数据跨度天数；远小于 requested_days 说明历史不足，需收敛档位 */
  available_days: number;
  /** 场内**未复权** OHLCV（画 K 线 + 成交量）；场外为空数组 → 前端改画净值线 */
  ohlc: ProductTrendOhlc[];
}

/** 取产品历史走势序列。空 dates/values 表示无数据，前端渲染空态而非报错。 */
export function getProductTrend(params: {
  symbol: string;
  range: TrendRange;
  /** 品类，由 resolve 返回后回传；后端据此选收盘价口径还是净值口径 */
  asset_type?: string;
  /** 显式起始日 YYYY-MM-DD（#2171 建仓期区间：首笔买入日至今）；给定时后端忽略 range 档位 */
  start?: string;
}) {
  return http.request<ApiResponse<ProductTrendResult>>(
    "get",
    "/api/products/trend/",
    { params }
  );
}

/** 买卖点（#2171 · 走势叠加层）。锚 T 日（trade_date），确认日随点返回 */
export interface TradePoint {
  /** 流水 ID（交易明细列连接键；老数据可能为 null） */
  txn_id: number | null;
  /** 交易日 YYYY-MM-DD（x 轴锚定用） */
  date: string;
  side: "buy" | "sell";
  /** 成交金额（元） */
  amount_yuan: number;
  /** 份额（份） */
  quantity: number;
  /** 成交价（元） */
  price_yuan: number;
  /** 手续费（元） */
  fee_yuan: number;
  /** 确认日（悬浮展示；可能为 null） */
  confirm_date: string | null;
  account_name: string | null;
  /** 该笔**之前**的持仓均价（元/份）；首笔前无持仓为 null——
      「低于当时成本线」空心编码的参照，无参照时不判 */
  cost_before_avg_yuan: number | null;
  /** 该笔之后的成本线值（元）；清仓笔为 0 */
  cost_after_yuan: number;
  /** 该笔后清仓（成本线在此中断） */
  closed: boolean;
}

/**
 * 成本线一点（#2171）：某交易日收盘后的持仓成本。
 *
 * ⚠️ **两个字段量纲不同，别混用**：
 * - `avg_cost_yuan` 单位成本（**元/份**）——**走势图成本线画的是它**（与净值同轴可比）；
 * - `cost_yuan` 持仓**总成本**（元，千级）——金额口径，供交易明细「当时成本」列。
 *
 * 首版只给了 `cost_yuan`，走势图把它当价格画：一条 10,000 元的成本线遇上 1.x 的净值，
 * y 轴被拉到万元级，整条净值曲线被压成贴着 0 的一条直线（用户反馈的
 * 「勾选买卖点后走势变成一条为 0 的直线」）。
 */
export interface CostLinePoint {
  date: string;
  /** 当日持仓单位成本（元/份）；当日无持仓不产出该点 */
  avg_cost_yuan: number;
  /** 当日持仓总成本（元）——金额口径，不要画进净值图 */
  cost_yuan: number;
}

/** 单笔流水的贡献明细（#2171 P1 · 交易明细「当时成本 / 收益贡献」两列的数据源） */
export interface TradeContribution {
  txn_id: number | null;
  /** 流水类型（buy / sell / dividend / dividend_cash / deposit / withdraw / dividend_reinvest） */
  kind: string;
  date: string;
  /** 该笔之后的持仓成本（元） */
  cost_after_yuan: number;
  /** 收益贡献（元）：买入=0；卖出=净回款−释放成本；分红/红利再投=+金额 */
  profit_contribution_yuan: number;
}

/** 累计收益线一点（#2171 P1）：某交易日收盘后的累计值 */
export interface ProfitLinePoint {
  date: string;
  /** 累计已实现盈亏（元）= 分红 + 净回款 − 释放成本；不做市值估计 */
  realized_yuan: number;
  /** 累计投入成本（元，含费）——收益率模式的分母 */
  invested_yuan: number;
}

export interface TradeTimelineSummary {
  buy_count: number;
  sell_count: number;
  dividend_count: number;
  total_buy_amount_yuan: number;
  total_sell_amount_yuan: number;
  total_fee_yuan: number;
  /** 现金分红总额（元；dividend 与 dividend_cash 两种写法合计） */
  total_dividend_yuan: number;
  /** 累计投入成本（元，含费）——收益率分母 */
  total_invested_yuan: number;
  /** 累计已实现盈亏（元）= 分红 + 净回款 − 释放成本 */
  realized_pnl_yuan: number;
  first_trade_date: string | null;
  last_trade_date: string | null;
  current_quantity: number;
  current_cost_yuan: number;
  /** 成本均价（元/份）；空仓为 null */
  current_avg_cost_yuan: number | null;
  /** 未参与重放的流水数（拆分 / 兑付等，不静默丢弃） */
  ignored_count: number;
  ignored_types: Record<string, number>;
}

export interface TradeTimelineResult {
  symbol: string;
  points: TradePoint[];
  cost_line: CostLinePoint[];
  /** 每笔流水的当时成本 + 收益贡献（P2 两列数据源；按 txn_id 关联） */
  contributions: TradeContribution[];
  /** 逐日累计已实现 + 累计投入（累计收益曲线数据源） */
  profit_line: ProfitLinePoint[];
  summary: TradeTimelineSummary;
}

/**
 * 取持仓交易时间线（#2171 · 详情页走势叠加买卖点 / 成本线）。
 *
 * 私有数据：未登录 / 无持仓 / 无流水均返回空 points + 空 cost_line（结构不变），
 * 调用方据 `points.length` 决定是否渲染叠加层，**不分支解析**。
 * `ledger_id` 不传 = 全部账户合并（产品级视角，与产品级 XIRR 同源）。
 */
export function getTradeTimeline(params: {
  symbol: string;
  ledger_id?: number;
}) {
  return http.request<ApiResponse<TradeTimelineResult>>(
    "get",
    "/api/products/trade-timeline/",
    { params }
  );
}
