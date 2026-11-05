// frontend/src/api/products/fund.ts
// 基金资料 / 绩效 / 行业与持仓明细（#2878 子域拆分；实现逐字搬自 api/products.ts，端点契约勿改）
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 基金经理条目（`/api/products/fund-profile/` 返回） */
export interface FundProfileManager {
  mgr_code: string;
  name: string;
  company: string | null;
  appointment_date: string | null;
  /** 代表作品标记（来自 fund_managers 关联表）。false = 只是该基金的经理之一 */
  is_classic: boolean;
}

/** 基金资料聚合结果（#1968）。字段缺失一律为 null，前端据此降级为「—」 */
export interface FundProfileResult {
  fund_code: string;
  name: string;
  full_name: string | null;
  /** 基金小类名（股票型 / 混合型…），直接是后端中文名，前端不另建映射表 */
  fund_type: string | null;
  /** 基金大类名 */
  fund_variety: string | null;
  /** 基金公司 */
  company: string | null;
  /** 首屏三项：单位净值 + 净值日期 + 日涨跌(%)。change_pct 为 null 表示**前一日净值缺失**，
      不是「今天没涨」——前端不可把它当 0 显示 */
  unit_nav: number | null;
  nav_date: string | null;
  prev_unit_nav: number | null;
  prev_nav_date: string | null;
  change_pct: number | null;
  /** 规模（亿元） */
  scale: number | null;
  /** 成立日期 YYYY-MM-DD */
  create_time: string | null;
  risk_level: number | null;
  benchmark: string | null;
  /** 晨星 3 年期星级 1~5（#1440）；null = 该基金无晨星评级（货基/新基金常态），
   *  不是「采集失败」。源为东财评级总汇页，与净值/费率链路口径不同，故单列。 */
  morningstar_rating: number | null;
  /** 晨星评级较上期变化（-4~4）；null = 未知。0 = 与上期持平（前端不展示） */
  morningstar_rating_delta: number | null;
  /** 评级快照日期 YYYY-MM-DD（东财页当日 / 最近一次变化日） */
  morningstar_rating_asof: string | null;
  /** 基金经理列表；缺字段时为 null（与接口契约一致：缺失一律降级为「—」） */
  managers: FundProfileManager[] | null;
  /** 费率阶梯；取不到时为 null（不阻断其余字段） */
  fee_rates: {
    fund_code: string;
    currency: string | null;
    /** 申购档：`rate` 为比例档（0.015 = 1.5%），`fee_amount` 为固定金额档（元/笔，
     *  与 rate 互斥；大额档常见「1000 元/笔」）。两者都要读，否则固定档会被当成 0%。 */
    purchase: {
      start_quota: number;
      end_quota: number | null;
      rate: number;
      fee_amount: number | null;
    }[];
    redeem: { start_day: number; end_day: number | null; rate: number }[];
  } | null;
  /** 数据来源站点名（如「天天基金」）；#1969 前脚注写的是 daily_worth 这类表名 */
  source: string;
}

/** 取基金资料聚合（详情页首屏 + 资料区块）。404 = 该代码不是基金。 */
export function getFundProfile(code: string) {
  return http.request<ApiResponse<FundProfileResult>>(
    "get",
    "/api/products/fund-profile/",
    { params: { code } }
  );
}

/** 区间收益切面条目（`/api/products/fund-performance/` 返回） */
export interface FundPerformanceInterval {
  /** 档位 key：1w/1m/3m/6m/1y/2y/3y/5y/ytd/since */
  key: string;
  /** 中文标签（近1周 / 成立以来…） */
  label: string;
  /** 区间收益率(%)；null = 该区间数据不足 */
  value: number | null;
}

/**
 * 基金业绩与风险（#2029 卡 B · 详情页业绩与风险卡）。
 *
 * - `fund_kind: "fund"`：场外基金，含区间收益切面 + 最大回撤（近3年）+ 年化波动率（近1年）；
 *   `applicable: false` 表示净值点不足，前端降级「暂无可展示的业绩数据」。
 * - `fund_kind: "money"`：货币基金，无回撤口径，改返 `annual_return_7d`（七日年化）+
 *   `nav_per_10k`（万份收益）；`basis: "money_fund"`。
 * 所有收益率/指标缺失一律为 null，前端据此降级为「—」。
 */
export interface FundPerformanceResult {
  fund_kind: "fund" | "money";
  /** 是否有可展示的业绩数据（场外基金净值点不足时为 false） */
  applicable: boolean;
  /** 口径标记：acc_nav / money_fund / insufficient */
  basis: string;
  /** acc_nav 口径说明（场外基金）：累计净值口径，非严格分红再投复权净值 */
  acc_nav_caveat?: string;
  /** 区间收益切面（仅 fund_kind=fund 且有数据时非空） */
  intervals: FundPerformanceInterval[];
  /** 最大回撤(%)（负数，如 -18.52）；样本不足为 null */
  max_drawdown: number | null;
  /** 回撤口径：fixed_3y / insufficient */
  max_drawdown_basis: string;
  /** 回撤窗口中文标签（如「近3年」） */
  max_drawdown_window: string | null;
  /** 回撤序列截至日 YYYY-MM-DD */
  max_drawdown_as_of: string | null;
  /** 近1年年化波动率(%)；样本不足为 null */
  volatility_1y: number | null;
  /** 数据截至日 YYYY-MM-DD */
  as_of: string | null;
  /** 数据来源站点名（如「天天基金」） */
  source: string;
  /** 货基：七日年化收益率(%)（仅 fund_kind=money） */
  annual_return_7d?: number | null;
  /** 货基：万份收益(元)（仅 fund_kind=money） */
  nav_per_10k?: number | null;
  /**
   * 货基：七日年化的窗口长度（自然日），恒为 7。
   * 刻意按**自然日**而非「最近 7 个观测」——后者会让国庆这类长假把窗口拉到 13 天。
   */
  window_days?: number;
  /** 货基：窗口内实际有几个已发布样本（节假日会 < window_days） */
  samples?: number;
  /** 货基：七日年化口径的人话说明，供脚注直接展示 */
  caliber_note?: string;

  /** 本轮回撤(%)：当前所处回撤区间（最近一次新高 → 最新一日）。0 = 正在新高，负 = 还在坑里 */
  current_drawdown?: number | null;
  /** 本轮回撤起点（最近一次净值新高日）YYYY-MM-DD */
  current_drawdown_peak_date?: string | null;
  /** 本轮自高点起熬过的自然日数（用户体感的是日历，不是 K 线根数） */
  current_drawdown_days?: number | null;
  /** 最大回撤高点日 YYYY-MM-DD */
  max_drawdown_peak_date?: string | null;
  /** 最大回撤低点日 YYYY-MM-DD */
  max_drawdown_trough_date?: string | null;
  /** 年化收益(%)（窗口与 risk_window 一致） */
  annual_return?: number | null;
  /** 年化波动率(%)——注意与上方「近1年」的 volatility_1y **窗口不同** */
  annual_volatility?: number | null;
  /** 夏普：(年化−rf)/年化波动。把上涨也算成风险，作参照用 */
  sharpe?: number | null;
  /** 索提诺：只罚下行波动（比夏普更贴买方） */
  sortino?: number | null;
  /** 卡玛：年化/|最大回撤| */
  calmar?: number | null;
  /** 溃疡指数 UI(%)：看整段煎熬而非单个最深处 */
  ulcer_index?: number | null;
  /** UPI：年化/UI（参考方简化式） */
  upi?: number | null;
  /** 波回比：年化/(波动×|最大回撤率|) */
  return_drawdown_ratio?: number | null;
  /** 胜率(%) */
  win_rate?: number | null;
  /** 胜率周期 day/week/month */
  win_rate_period?: string | null;
  /** 胜率是否基于重叠滚动窗口（是 ⇒ 持有体验，不可当概率读） */
  win_rate_overlap?: boolean;
  /** 风险指标窗口标签（如「近3年」）——跨基金比较前必须确认窗口一致 */
  risk_window?: string | null;
  /** 参与计算的净值点数（样本量透明） */
  risk_sample_points?: number;
  /** 无风险利率（年化小数）：不告诉用户 rf 取多少的夏普不可复核 */
  risk_free_rate?: number;
  /** 风险口径：acc_nav / distorted（检出净值跳变，疑似份额折算/大额赎回） */
  risk_basis?: string | null;
  /** 口径提示（逐条展示：含 rf 取值、跳变告警、分母退化说明） */
  risk_caveats?: string[];
  /** 数值来源：snapshot（每日快照）/ computed（快照缺失时现算回退） */
  risk_source?: "snapshot" | "computed";

  // ── 基准相对块（#167 追加之二）────────────────────────────────────────
  // 基准按 fund_type 映射（**不解析** fund.benchmark 那句自然语言），
  // 债基对债指数、股基对同类股基指数。`null` = 本基金不适用基准
  // （货基 / 指数型 / QDII —— 它们该比的是跟踪标的，而我们没有标的指数数据，
  // 所以**不给**而不是拿沪深300 顶替）。
  benchmark?: FundBenchmark | null;
  /**
   * 同类内分位（百分位 0~100，**越大越好**）。
   *
   * 为什么需要它：风险比跨类别不可比（债基波动天生小 ⇒ 夏普系统性偏高），
   * 绝对值不能跨类读，而「在同类里排前 10%」对任何类别都是同一句话。
   * 缺失的指标不出现在这里（同类样本 < 5 时后端不出分位）——降级为「—」。
   */
  peer_percentiles?: Record<string, number> | null;

  // ── 拟涨幅2（#167 收尾）──────────────────────────────────────────────
  /**
   * 拟涨幅2：近 1 月 / 3 月 / 6 月 / 1 年四段**互不重叠**收益的加权连乘。
   *
   * 为什么去重叠：这四个滚动涨幅彼此包含，直接加权会把同一段行情数上多遍。
   * `null` = 历史不足一年（**不拿「成立以来」凑**）或样本不足，降级为「—」。
   */
  shape_gain2?: ShapeGain2 | null;
}

/** 取基金业绩与风险。404 = 该代码不是基金。 */
export function getFundPerformance(code: string) {
  return http.request<ApiResponse<FundPerformanceResult>>(
    "get",
    "/api/products/fund-performance/",
    { params: { code } }
  );
}

/**
 * 基金行业配置 + 持仓明细（#2029 卡 C · 详情页行业配置卡 + 持仓明细卡）。
 *
 * 口径（后端 `services/fund_holdings_detail.py` 定，前端只呈现）：
 * - `industries` **按 scheme 分区**：csrc（证监会门类，主口径）与 gics（GICS 板块）
 *   语义不重叠，**禁止跨体系相加**；`is_primary` 标出主口径，非主口径仅参考。
 * - `holdings.basis` 为披露口径：`full`（半年报/年报全量）/ `top10`（季报前十大），
 *   同期间并存时优先 `full`。`basis_label` 必须展示给用户 —— 否则会把
 *   「只披露了 10 只」误读成「只买了 10 只」。
 * - 所有字段缺失一律 null，前端据此降级为「—」。
 */
export interface FundIndustryItem {
  industry_code: string;
  industry_name: string;
  /** 占净值比例(%)；缺失为 null（不按 0 参与合计） */
  ratio: number | null;
}

export interface FundIndustryBucket {
  /** csrc（证监会门类）/ gics（GICS 板块） */
  scheme: string;
  scheme_label: string;
  /** 是否主口径（true 的那个才进环形图） */
  is_primary: boolean;
  report_period: string | null;
  report_date: string | null;
  items: FundIndustryItem[];
  /** 该分区占比合计(%) */
  total_ratio: number | null;
}

export interface FundHoldingRow {
  rank: number | null;
  stock_code: string;
  stock_name: string | null;
  /** 占净值比例(%) */
  ratio: number | null;
  /** 持股数(万股) */
  shares: number | null;
  /** 持仓市值(万元) */
  market_value: number | null;
}

export interface FundHoldingsDetailResult {
  fund_code: string;
  fund_name: string | null;
  /** 是否有任一类可展示数据（行业配置或持仓明细） */
  applicable: boolean;
  has_industry: boolean;
  has_holding: boolean;
  /** 按 scheme 分区的行业配置，主口径排第一 */
  industries: FundIndustryBucket[];
  /** 环形图数据（只含主口径，且已与表格同口径截断） */
  industry_chart: Array<{ name: string; value: number }>;
  holdings: {
    rows: FundHoldingRow[];
    /** full / top10 / unknown */
    basis: string | null;
    /** 中文口径标签，必须展示 */
    basis_label: string | null;
    report_period: string | null;
    report_date: string | null;
    /** 所示条目的占比合计(%) */
    shown_total_ratio: number | null;
  };
  as_of: string | null;
  /** 数据来源站点名（东财 f10，非净值链路的天天基金） */
  source: string;
}

/** 取基金行业配置 + 持仓明细。404 = 该代码不是基金。 */
export function getFundHoldingsDetail(code: string) {
  return http.request<ApiResponse<FundHoldingsDetailResult>>(
    "get",
    "/api/products/fund-holdings-detail/",
    { params: { code } }
  );
}

/** 拟涨幅2 结果（#167 收尾）。`segments` 是四段原始收益（%），随值下发供复核。 */
export interface ShapeGain2 {
  /** 拟涨幅2（%） */
  shape_gain2: number;
  /** 四段去重叠收益（%），近 → 远 */
  segments: number[];
  /** 口径说明（权重与「不含 rf」） */
  basis: string;
}

/** 基准相对块（#167）。`available: false` 表示基准已选定但序列暂缺，**不以上述以外的指数顶替** */
export interface FundBenchmark {
  /** 基准指数代码（`index_daily.index_code`），如 `000300.SH` / `885001.WI` */
  code: string;
  /** 基准展示名（后端下发，前端不抄映射） */
  name: string;
  /** 命中规则名——口径留痕：用户可复核「凭什么拿它比」 */
  matched_by: string;
  /** 序列是否可用 */
  available: boolean;
  /** 不可用时的原因（仅 available=false） */
  reason?: string;
  /** 共同交易日上的样本数（仅 available=true） */
  sample_points?: number;
  /** 基准同期年化收益(%) */
  bench_annual_return?: number | null;
  /** 基金同期年化收益(%) */
  fund_annual_return?: number | null;
  /** 超额收益(%)：基金 − 基准 */
  excess_return?: number | null;
  /** 年化跟踪误差(%) */
  tracking_error_annual?: number | null;
  /** 信息比率：年化超额 / 年化跟踪误差 */
  information_ratio?: number | null;
  /** 上行捕获率(%)：>100 = 基准涨时它涨得更多 */
  upside_capture?: number | null;
  /** 下行捕获率(%)：<100 = 基准跌时它跌得更少 */
  downside_capture?: number | null;
  /** 口径标记：ok / insufficient（共同交易日不足） */
  basis?: string;
}
