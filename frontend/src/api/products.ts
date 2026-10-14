// frontend/src/api/products.ts
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 产品身份解析结果（#1963 后端契约，#1964 消费） */
export interface ProductResolveResult {
  symbol: string;
  asset_type: string;
  market: string;
  venue: string;
  display_name: string;
  /** 未登录为 null（端点是「可选登录」端点），不可当 false 用——那是「未知」不是「没有」 */
  in_watchlist: boolean | null;
  /** 同 in_watchlist */
  has_position: boolean | null;
  /** 判定来源：watchlist / position / catalog / hint，仅供排查 */
  source: string;
}

export interface ProductResolveParams {
  symbol: string;
  /** 市场消歧（同品类跨市场同码，如 000001） */
  market?: string;
  /** 交易场所消歧（EXCHANGE / OTC） */
  venue?: string;
  /** 入口提示的前端路径段品类；后端判定优先于此，仅在目录查不到时兜底 */
  asset_type?: string;
}

/** 解析产品身份。404 = 未识别的产品代码（前端走空态，不是白屏）。 */
export function resolveProduct(params: ProductResolveParams) {
  return http.request<ApiResponse<ProductResolveResult>>(
    "get",
    "/api/products/resolve/",
    { params }
  );
}

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
  /** 基金经理列表；缺字段时为 null（与接口契约一致：缺失一律降级为「—」） */
  managers: FundProfileManager[] | null;
  /** 费率阶梯；取不到时为 null（不阻断其余字段） */
  fee_rates: {
    fund_code: string;
    currency: string | null;
    purchase: { start_quota: number; end_quota: number | null; rate: number }[];
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

/**
 * 指数资料聚合结果（#2028 · `/api/products/index-profile/`）。
 *
 * 字段缺失一律 null，前端降级「—」。分位是**读路径现算**（乐咕月频近 5 年窗口，
 * #1407 拍板）：样本不足 12 点时 pe_percentile 为 null——那是「样本不够」不是
 * 「分位为 0」，两者语义相反，不可混。股息率分位本期恒为 null（乐咕无该序列）。
 */
export interface IndexProfileResult {
  /** 裸 6 位指数码（service 已归一，带前缀入口也返回裸码） */
  index_code: string;
  /** 指数中文简称（index_catalog.name） */
  name: string;
  /** 编制/发布机构中文名（中证指数公司 / 国证指数…）；未知为 null */
  publisher_label: string | null;
  /** 核心指数白名单标记（自选分组置顶用，此处仅展示「核心」徽标） */
  is_core: boolean;
  /** 市盈率（中证官方口径 pe_1，最新一期）；无官方估值文件为 null */
  pe: number | null;
  /** 股息率(%)（中证官方口径 dividend_yield_1）；为 null 时不可显示为 0 */
  dividend_yield: number | null;
  /** 估值日期 YYYY-MM-DD（官方文件最新一期） */
  valuation_date: string | null;
  /** PE 历史分位(%)：乐咕滚动 PE 在近 5 年月频窗口中的位置；样本不足为 null */
  pe_percentile: number | null;
  /** 分位口径元数据（脚注直接展示，前端不另建映射） */
  percentile_metric: string | null;
  /** 分位基线的最新采样日 YYYY-MM-DD */
  percentile_date: string | null;
}

/** 取指数资料聚合。404 = 该代码不在指数名录。 */
export function getIndexProfile(symbol: string) {
  return http.request<ApiResponse<IndexProfileResult>>(
    "get",
    "/api/products/index-profile/",
    { params: { symbol } }
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

/** 股票资料聚合结果（#1969 · 详情页股票区块）。字段缺失一律为 null，前端据此降级为「—」 */
export interface StockProfileResult {
  symbol: string;
  name: string;
  market: string | null;
  /** 品类（后端 securities.type），如 stock / etf；前端不另建映射表 */
  asset_type: string;
  currency: string | null;
  /** 行业 / 板块；securities.sector 填充率有限，缺失时降级「—」而不是编造 */
  sector: string | null;
  /** 区间统计窗口（**交易日条数**，非自然日）：后端默认 60 */
  window_days: number;
  /** 行情日期 YYYY-MM-DD；无行情为 null */
  quote_date: string | null;
  /** 最新收盘价（优先前复权 adj_close）；无行情为 null */
  close: number | null;
  /** 区间最高 / 最低（**未复权原值**，与持仓页「当日最高/最低」同口径） */
  high: number | null;
  low: number | null;
  /** 区间涨跌幅(%)（窗口首日 → 最新）。null 表示首日缺失或为 0，**不是「没涨」** */
  change_pct: number | null;
  /** 前一个**有收盘价**的交易日收盘（停牌时即最后交易日收盘，与行情软件「昨收」同口径）。
      窗口内只有 1 条行情时为 null —— 没有基准就不给日涨跌 */
  prev_close: number | null;
  /** 日涨跌额 = close − prev_close；null 表示缺基准，**不是「没涨跌」** */
  change_amount: number | null;
  /** 日涨跌幅(%)（昨收 → 最新）；给「最新收盘」上色用的就是这个口径，不是区间口径 */
  day_change_pct: number | null;
  /** 实际参与统计的交易日条数；小于 window_days 说明上市/历史不足，需如实提示 */
  trading_days: number;
  /** 数据来源站点名（如「新浪财经」）；一条行情都没有时为空串 */
  source: string;
  /** 口径说明（前复权收盘价 / 未复权高低） */
  basis: string;
}

/**
 * 取股票资料聚合（详情页股票区块）。
 *
 * 只补 `/trend/` 给不出的东西（基本资料 + 区间高低）：走势曲线仍由
 * `getProductTrend` 取，本端点**不返回序列**，同页不会出现两条行情取数链路。
 * 无行情不是错误（资料照常返回、行情字段为 null），仅代码不存在才 404。
 */
export function getStockProfile(params: { symbol: string; market?: string }) {
  return http.request<ApiResponse<StockProfileResult>>(
    "get",
    "/api/products/stock-profile/",
    { params }
  );
}

/** 任职基金条目（`/api/products/manager-profile/` 返回） */
/**
 * 展示换算结果（#1970 扩展 · 后端转换层 `services/tenure_display.py`）。
 *
 * **为什么前端不再自己换算**：后端存的是为计算而存的原始值（如从业天数 5125、
 * 规模 307.94），界面要的是给人看的解读（「14 年又 15 天」）。换算收口在后端单点，
 * 改口径不会漏改某个页面 —— 前端再写一次 `÷365` 正是要消灭的那种重复。
 *
 * `basis` 必须被消费：没有口径的数字等于假数字（详见各字段注释）。
 */
export interface TenureDisplay {
  /** 数值年（供前端排序/比较，不用于直接展示） */
  years: number;
  /** 展示文本，如「14 年又 15 天」（与天天基金 F10 口径逐字对齐） */
  text: string;
  /**
   * 口径标记：
   * - `em_days_derived`：由东财「累计从业时间」反推的**首次任职日**，
   *   为**日历跨度**，公转私/ 断档**不扣减**；
   * - `derived_from_start`：由库内任期起始日反推（无东财数据时的降级路径）。
   *
   * ⚠️ `em_days_derived` 的日期有 **±1 天不确定性**（基准日与东财统计截止日
   * 可能差一天，实测跨零点重跑会整体偏移）。故界面**不可**宣称「精确到 X 月 X 日
   * 开始任职」这类精确表述；「从业 N 年」不受影响。
   */
  basis: "em_days_derived" | "derived_from_start";
  /**
   * 溯源原值，由起始日**反算**回的天数（**非数据库原值** —— `managers` 表没有
   * `tenure_days` 列，天数只是入站数据不入库）。与东财原始天数的差异在 **±1 天**内。
   *
   * 仅供审计/展示辅助，**不要当精确溯源使用**。
   */
  raw: number | null;
  start_date: string;
  as_of: string;
}

/** 规模展示值。⚠️ 口径：仅该经理**现任**基金合计，不含已卸任基金 */
export interface ScaleDisplay {
  text: string;
  value: number;
  unit: "亿元";
  basis: string;
}

/** 回报展示值。`value` 带符号（负数为跌），前端按符号选 `--color-rise/fall` */
export interface ReturnDisplay {
  /** 显式带符号，如 `+43.59%` / `-18.52%` */
  text: string;
  value: number;
  basis: string;
}

export interface ManagerProfileFund {
  fund_code: string;
  name: string;
  /** 代表作品标记（来自 fund_managers 关联表） */
  is_classic: boolean;
  /** 任职起止：来自天天基金 F10（#1970 扩展前实测填充率 0%，恒为 null） */
  start_date: string | null;
  end_date: string | null;
  /**
   * 在任标记 = 未记录卸任日（#1970 扩展）。
   *
   * **不能改用东财全量表的「现任基金」**：实测张坤已于 2026-05-22 卸任蓝筹精选，
   * 但 `fund_manager_em` 仍把他列为该基金现任（粗粒度、不含卸任时间）。
   */
  is_active: boolean;
  /** 本基金任期时长（口径见 TenureDisplay.basis） */
  tenure_display: TenureDisplay | null;
}

/** 基金经理资料聚合结果（#1970）。字段缺失一律为 null，前端据此降级为「—」 */
export interface ManagerProfileResult {
  mgr_code: string;
  name: string;
  /** 重名靠公司消歧（库内 119 组重名，最多 6 位同名） */
  company: string | null;
  /** 公司全称（AMAC 公示口径，覆盖低于简称，允许为 null） */
  company_full_name: string | null;
  /** 公司整体管理规模（亿元）。⚠️ 与本人 sum_scale 不同口径，勿当作「占比」解读 */
  company_scale: number | null;
  mgr_type: string | null;
  /**
   * 首次任职日（由 tenure_days 反推落库）。
   *
   * ⚠️ ① 是**职业起点**，不是基金级任职起始（后者在 `funds[].start_date`）；
   * ⚠️ ② 为**误差 ≤1 天的估计值**（基准日与东财统计截止日可能差一天），
   *    不可当精确日期对外表述。
   */
  appointment_date: string | null;
  /** 以下为原始值（亿元 / %），保留供交叉校验；**展示请用 *_display** */
  sum_scale: number | null;
  best_return: number | null;
  avatar_url: string | null;
  // ── 展示档（转换层产出，优先消费这些）──
  /** 从业年限。以**首次任职日**为基准，非各基金任期起算 */
  tenure_display: TenureDisplay | null;
  scale_display: ScaleDisplay | null;
  best_return_display: ReturnDisplay | null;
  /** 任职基金**总数**（非返回条数——列表有 fund_limit 上限，两者不同） */
  fund_count: number;
  /** **已列出条目中**的在任数（受 fund_limit 截断，不是全量在任数） */
  active_fund_count: number;
  funds: ManagerProfileFund[];
}

/** 基金经理资料。入参是 mgr_code 而非姓名（库内重名，姓名不是唯一键）。 */
export function getManagerProfile(params: {
  mgr_code: string;
  fund_limit?: number;
}) {
  return http.request<ApiResponse<ManagerProfileResult>>(
    "get",
    "/api/products/manager-profile/",
    { params }
  );
}

/** 代表作重仓单行 */
export interface ManagerHoldingRow {
  rank: number | null;
  stock_code: string;
  stock_name: string | null;
  /** 占净值比例（%） */
  ratio: number | null;
  /** 持仓市值（万元） */
  market_value: number | null;
}

/**
 * 风格标签（#2044）。
 *
 * - `dim`/`key` 是稳定枚举，前端按 `key` 映射 Badge 样式；
 * - 后端**不返回颜色**（配色由前端令牌决定，硬约束）；
 * - 数据不足的维度**缺席**而非 null——`style_labels` 里找不到该 `dim` 即该维度
 *   无数据，展示层按维度缺席处理（不渲染占位徽章）。
 */
export interface StyleLabel {
  /** 维度：`concentration` 持仓集中度 / `industry` 行业集中度 / `size` 市值风格 */
  dim: string;
  /** 稳定标签枚举，如 `concentration_high` / `size_large` */
  key: string;
  /** 中文短文案，如「持仓高集中」 */
  label: string;
  /** 可解释依据，如「前十大重仓占净值 65.8%，全库 P80」（hover/副文本展示） */
  basis: string;
}

/** 代表作前十大重仓结果（#1970 扩展 · `manager-holdings` 端点） */
export interface ManagerHoldingsResult {
  fund_code: string | null;
  fund_name: string | null;
  /** 报告期，如 2026Q2 */
  report_period: string | null;
  /** 报告期截止日 */
  report_date: string | null;
  /** 口径：`full` 全量披露 / `top10` 季报前十大 */
  basis: "full" | "top10" | null;
  /**
   * 口径中文标签，**必须展示**。
   *
   * 为什么：用户看到「十大重仓」时需要知道这是季报口径（只披露了 10 只）
   * 还是半年报全量，否则会把「只披露 10 只」误读成「只买了 10 只」。
   */
  basis_label: string | null;
  /** 前 N 大合计占净值比（集中度锚点） */
  total_ratio: number | null;
  rows: ManagerHoldingRow[];
  /** 风格标签（#2044）：纯函数判据 + 全库标定阈值，数据不足维度缺席 */
  style_labels: StyleLabel[];
  /** 无数据时的原因（固定契约：rows 为空即无数据，不是接口错误） */
  empty_reason?: string;
}

/**
 * 代表作前十大重仓。入参与 manager-profile 一致（mgr_code 而非姓名）。
 *
 * 为什么独立端点：重仓要按 fund_code 查最新报告期，是独立重查询；
 * 经理区块首屏并不总需要它，拆开后前端可按需决定发不发。
 */
export function getManagerHoldings(params: {
  mgr_code: string;
  fund_limit?: number;
}) {
  return http.request<ApiResponse<ManagerHoldingsResult>>(
    "get",
    "/api/products/manager-holdings/",
    { params }
  );
}

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
export type TrendRange = "1M" | "3M" | "6M" | "1Y";

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
}) {
  return http.request<ApiResponse<ProductTrendResult>>(
    "get",
    "/api/products/trend/",
    { params }
  );
}

/** 买卖点（#2171 · 走势叠加层）。锚 T 日（trade_date），确认日随点返回 */
export interface TradePoint {
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
  /** 该笔之后的成本线值（元）；清仓笔为 0 */
  cost_after_yuan: number;
  /** 该笔后清仓（成本线在此中断） */
  closed: boolean;
}

/** 成本线一点：某交易日收盘后的持仓成本（元） */
export interface CostLinePoint {
  date: string;
  cost_yuan: number;
}

export interface TradeTimelineSummary {
  buy_count: number;
  sell_count: number;
  dividend_count: number;
  total_buy_amount_yuan: number;
  total_sell_amount_yuan: number;
  total_fee_yuan: number;
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

/**
 * 投顾组合档案（#1975 · 详情页投顾组合区块）。字段名跟随后端/库的 snake_case 契约。
 *
 * 可得性（本机真实库 105 个组合实测）：`org_name` / `risk_level` / 区间收益 /
 * 回撤 / 波动率 / 夏普 填充率 **91~100%**；而 `strategy_type` / `cum_return` /
 * `running_days` / `benchmark` / `excess_return` 为 **0%**、`host` **1.9%**、
 * `return_ytd` **2.9%** —— 前端一律降级「—」，不编造占位值（设计 §6 诚实降级）。
 *
 * `holding_count` / `adjust_count` 供区块判断「成分基金 / 调仓记录」要不要渲染、
 * 请求要不要发：实测调仓只覆盖 **16/105** 个组合，多数组合**「没有调仓」才是常态**。
 */
export interface AdvisorProfileResult {
  code: string;
  name: string;
  /** 平台码（QIEMAN / TIANTIAN…）；中文标签走 constants/advisorPlatform */
  platform: string;
  org_name: string | null;
  /** 主理人；实测填充率仅 1.9%，故识别主要靠「名称 + 平台 + 机构」 */
  host: string | null;
  risk_level: string | null;
  product_type: string | null;
  strategy_type: string | null;
  strategy_summary: string | null;
  strategy_desc: string | null;
  /** 配置目标（五笔钱词表：liquid / stable / longterm…） */
  allocation: string | null;
  estab_date: string | null;
  running_days: number | null;
  benchmark: string | null;
  excess_return: number | null;
  nav: number | null;
  nav_date: string | null;
  source_url: string | null;
  is_active: boolean;
  cum_return: number | null;
  annual_return: number | null;
  return_1d: number | null;
  return_1w: number | null;
  return_1m: number | null;
  return_1q: number | null;
  return_6m: number | null;
  return_1y: number | null;
  return_ytd: number | null;
  return_since_incep: number | null;
  max_drawdown: number | null;
  volatility: number | null;
  sharpe_ratio: number | null;
  holding_count: number;
  adjust_count: number;
}

/**
 * 取投顾组合档案（详情页投顾组合区块首屏）。
 *
 * 只回答「这是个什么组合」；「持什么 / 调过什么」走**已上线**的
 * `getAdvisorHoldings` / `getAdvisorAdjusts`（自选速览抽屉在用的同一对端点），
 * 本函数不重复搬数据 —— 但返回的条数可让调用方先判断要不要发那两个请求。
 */
export function getAdvisorProfile(params: { code: string }) {
  return http.request<ApiResponse<AdvisorProfileResult>>(
    "get",
    "/api/products/advisor-profile/",
    { params }
  );
}
