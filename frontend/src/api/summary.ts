// src/api/summary.ts
import { http } from "@/utils/http";
import type { ApiResponse, SummaryData } from "./types";

const BASE_URL = "/api/summary/";

/**
 * 获取首页仪表盘聚合数据。
 * `memberId`（#1173）：按家庭成员切片；不传 = 家庭级全量。
 */
export function getSummary(memberId?: number) {
  return http.request<ApiResponse<SummaryData>>(
    "get",
    BASE_URL + (memberId ? `?member_id=${memberId}` : "")
  );
}

/** 桑基图数据 */
export type SankeyData = {
  nodes: Array<{ name: string; itemStyle?: { color: string } }>;
  links: Array<{ source: string; target: string; value: number }>;
};

/** 获取桑基图节点与链接数据 */
export function getSankeyData() {
  return http.request<ApiResponse<SankeyData>>("get", BASE_URL + "sankey/");
}

/** 分布分布聚合项：{name, value} */
export type DistributionItem = { name: string; value: number };

/** 家庭级多维市值分布（后端唯一聚合出口，Overview/资产总览分布图表消费） */
export type DistributionsData = {
  type_distribution: DistributionItem[];
  allocation_distribution: DistributionItem[];
  market_distribution: DistributionItem[];
  account_distribution: DistributionItem[];
  category_distribution: DistributionItem[];
  liability_distribution: DistributionItem[];
  total_assets: number;
  total_liabilities: number;
  net_worth: number;
  positions_total_mv: number;
};

/** 获取家庭级多维市值分布 */
/** 家庭级多维市值分布（`memberId`：按家庭成员切片，#1173） */
export function getDistributions(memberId?: number) {
  return http.request<ApiResponse<DistributionsData>>(
    "get",
    BASE_URL + "distributions/" + (memberId ? `?member_id=${memberId}` : "")
  );
}

/** 分组明细项（持仓或通用资产） */
export type GroupItem = {
  id: number;
  name: string;
  symbol?: string;
  asset_type?: string;
  type_label?: string;
  market?: string;
  market_label?: string;
  allocation?: string;
  allocation_label?: string;
  account_name?: string;
  quantity?: number;
  current_price?: number;
  market_value: number;
  pnl: number;
};

/** 维度分组（type/account/allocation），含 items 明细，后端聚合 */
export type PositionGroup = {
  name: string;
  total: number;
  total_pnl: number;
  count: number;
  items: GroupItem[];
};

export type GroupDimension = "type" | "account" | "allocation";

/** 获取持仓/资产按维度分组汇总（含 items 明细，后端唯一聚合出口） */
/** 持仓/资产分组明细（`memberId`：按家庭成员切片，#1173） */
export function getPositionGroups(
  dimension: GroupDimension,
  memberId?: number
) {
  return http.request<ApiResponse<PositionGroup[]>>(
    "get",
    BASE_URL + "groups/",
    {
      params: {
        dimension,
        ...(memberId ? { member_id: memberId } : {})
      }
    }
  );
}

/**
 * 资产快照单条（金额元；同比百分比后端计算，无历史为 null）
 *
 * #2132：快照记的是「**落库那一刻**的当前状态」，`snapshot_date` 只是标签——
 * 改持仓后历史不会更新，回填还会把今天的值贴到历史日期上。要「截至某日」的
 * 可回溯时点序列用 `getPnlCalendar`（后端 `pnl_snapshot_store`），两者不可混用。
 *
 * 本类型**只声明被消费的字段**：后端还返回 `realized_pnl` / `unrealized_pnl` /
 * `total_pnl` / `money_fund_income` 四列，但它们读的是流水 `realized_pnl` 列
 * （存量库全 0，与真零盈亏不可区分），与「已落袋表现」的 FIFO 自算口径不等价，
 * 故**刻意不声明、不消费**（见 docs/spec/tech-debt.md）。
 */
export type AssetSnapshotItem = {
  id: number;
  /** 账户ID；null=家庭级快照，非 null=该账户的账户级快照（#1181） */
  ledger_id: number | null;
  snapshot_date: string;
  total_assets: number;
  total_liabilities: number;
  net_worth: number;
  monthly_change_pct: number | null;
  yearly_change_pct: number | null;
};

/** 记录当日资产快照（幂等 upsert；可选 snapshot_date 回填，默认今天） */
export function postSnapshot(snapshot_date?: string) {
  return http.request<ApiResponse<AssetSnapshotItem>>(
    "post",
    BASE_URL + "snapshots/",
    {
      data: snapshot_date ? { snapshot_date } : {}
    }
  );
}

/**
 * 查询资产快照列表（升序，含同比；可选 start_date/end_date 闭区间）
 *
 * #1181：传 ledger_id 返回该账户的账户级序列；不传返回家庭级序列（既有行为）。
 */
export function getSnapshots(params?: {
  start_date?: string;
  end_date?: string;
  ledger_id?: number;
}) {
  return http.request<ApiResponse<AssetSnapshotItem[]>>(
    "get",
    BASE_URL + "snapshots/",
    {
      params
    }
  );
}

/**
 * #1812 收益日历单日状态（#1917 加 `partial`、#1942 拆「休市/没数据」，**缺数据绝不可画成 0**）
 *
 * - `updown`      有价且有持仓，当日盈亏非零
 * - `zero`        有价，当日盈亏恰为 0
 * - `partial`     **部分断档**（#1917 C 方案）：当天有标的有真报价、也有标的没有
 *   ⇒ **照常给出数值**，只是标注「数据不完整」。不可与 `closed` 合并——
 *   「有数据但不完整」与「无数据」对用户是完全不同的含义
 * - `no_price`    该标的整段无历史价格序列（`valuation_mode='balance'` 的银行理财/
 *   投顾/实物等，市值来自 `market_value_override` 单值非序列）
 * - `no_data`     **A 股开盘日**却一个可用价都取不到（净值未发布 / 每日同步任务没跑）。
 *   用户能处置（去跑同步），与「休市」不是一回事
 * - `no_position` 当天没有持仓（建仓前 / 清仓后）
 * - `closed`      **非 A 股开盘日**（周末 / 法定节假日 / 调休补班的周末）。
 *   判据是后端 `core/trading_calendar.is_trading_day()`，**不是**「当天有没有价格」
 *
 * #1942 之前 `no_data` 与 `closed` 共用一个状态码，UI 一律显示「休市」，
 * 于是「数据没同步」被读成「市场关门」。三方分工：
 * **有值但不全 → `partial`；一个值都没有 → 开盘日 `no_data` / 非开盘日 `closed`。**
 */
export type PnlCalendarState =
  | "updown"
  | "zero"
  | "partial"
  | "no_price"
  | "no_data"
  | "no_position"
  | "closed";

/** 收益日历单日 */
export type PnlCalendarDay = {
  date: string;
  /** 当日盈亏（元）；`null` = 不可算（无价格序列 / 休市 / 区间首日），**不是 0** */
  daily_pnl: number | null;
  /** 当日净资产（元） */
  net_worth: number;
  /** 当日收益率（%）；分母为前一日净资产，`null` = 首日或分母为 0 */
  rate: number | null;
  state: PnlCalendarState;
  /**
   * 当日行按收盘估值预估（#2141 收盘估值定格回退；后端 `day_uses_estimate` 落点）。
   * 仅当日行可能为 true，物化期间行永远没有——徽标据此展示，前端不按日期自行推断。
   */
  estimated?: boolean;
};

/**
 * 收益序列粒度（#1925 日 / 月 / 年三视图）
 *
 * - `day`    逐日明细回 `days`
 * - `month`  按自然月聚合成 `periods`，**不回日明细**
 * - `year`   按自然年聚合成 `periods`，**不回日明细**
 *
 * 月 / 年不是另算的一条口径，而是同一条日序列的两种切法——聚合在后端做，
 * 前端只负责呈现，禁止二次盈亏计算。
 */
export type PnlCalendarGranularity = "day" | "month" | "year";

/**
 * 收益日历期间（月 / 年粒度）
 *
 * `period` 的**键长即粒度**：`YYYY-MM`（月）/ `YYYY`（年），
 * 柱状标签据此推导，不必另传一个可能与数据对不上的展示字段。
 */
export type PnlCalendarPeriod = {
  period: string;
  /** 期间盈亏（元）；`null` = 该期间一天都算不出来（无价 / 休市），**不是 0** */
  pnl: number | null;
  /** 期间末净资产（元） */
  net_worth: number;
  /** 期间收益率（%）；分母为**上一期间末**净资产，`null` = 无基线或基线为 0 */
  rate: number | null;
  state: PnlCalendarState;
};

/**
 * 收益日历序列（后端 as-of 派生，**前端不做二次盈亏计算**）
 *
 * 口径：`daily_pnl` = `total_pnl` 的日差分，**不是** `net_worth` 日环比。
 * 前者对存取款免疫（建仓瞬间未实现盈亏为 0，追加投入不改变盈亏总额）；
 * 后者会被资金流污染（存入 10 万当天凭空「赚」10 万）。展示时须写明这一点。
 */
export type PnlCalendarSeries = {
  ledger_id: number | null;
  scope: "family" | "ledger";
  /** 请求区间（月 / 年粒度下，后端为取首期间收益率基线多算的一天**不在**此列 */
  start_date: string;
  end_date: string;
  /**
   * 区间内日盈亏合计（元）。
   * 字段名 `month_total` 是 #1812 留下的历史名，语义一直是**区间合计**；
   * 月 / 年粒度下同样是该区间合计，不是「某一个月」。
   */
  month_total: number;
  /**
   * 区间收益率（%，#1942 ②）：「金额 / 收益率」切换后合计行显示的那个数。
   *
   * 分母是**区间前一天**净资产——与首个期间的 `rate` 同分母，而不是把日收益率相加
   * （那会算错复利）。`null` = 不可算：无基准（区间前一天取不到价）或区间内
   * 一个可算日都没有。**不可算不是 0%**，前端须显示占位而不是 0.00%。
   */
  range_rate: number | null;
  /** 本次请求的粒度（#1925）；不传时后端缺省回 `day` */
  granularity: PnlCalendarGranularity;
  /** 区间内是否存在可计价持仓（false = 整段无价格序列，前端应显示空态而非零收益） */
  has_any_price: boolean;
  /**
   * 覆盖率诊断 —— 前端据此区分两种「空」：
   * - `priced_positions === 0` 且 `latest_price_date` 为空 ⇒ **数据缺口**（该月没跑快照）
   * - `priced_positions === 0` 但有价格数据 ⇒ 持仓按日无估值序列（理财/实物等）
   * 混成一句话会把前者说成「你的持仓有问题」。
   */
  coverage: {
    total_positions: number;
    priced_positions: number;
    unpriced_positions: number;
  };
  /** 区间内可用的最新价格日（ISO）；空 = 该区间一条价格数据都没有 */
  latest_price_date: string | null;
  /**
   * 「投资以来」的起点（ISO，#1942）：最早一笔改变份额的流水的生效日。
   * 年视图据此取全区间（一格一年），**不再由前端写死年数窗口**；
   * 无持仓 / 无流水时为 `null`，前端回落到「今年」。
   */
  first_txn_date: string | null;
  /** 逐日明细；`month` / `year` 粒度恒为空数组（聚合下推，不回日明细） */
  days: PnlCalendarDay[];
  /** 期间聚合；`day` 粒度恒为空数组 */
  periods: PnlCalendarPeriod[];
};

/**
 * 查询收益日历（#1812 / #1925）
 *
 * 与 `getSnapshots` 的区别：快照表记的是「落库当日那一刻的当前状态」，
 * 改持仓后历史**不会**更新，回填还会把今天的值贴到历史日期上；
 * 本接口从流水 + 历史价格现算，改持仓后历史自动跟着变。
 *
 * 传 `ledger_id` 返回该账户级序列；不传返回家庭级。
 * 传 `granularity` 决定回 `days` 还是 `periods`（见 `PnlCalendarGranularity`）。
 */
export function getPnlCalendar(params?: {
  start_date?: string;
  end_date?: string;
  ledger_id?: number;
  granularity?: PnlCalendarGranularity;
}) {
  return http.request<ApiResponse<PnlCalendarSeries>>(
    "get",
    BASE_URL + "pnl-calendar/",
    {
      params
    }
  );
}

/** #2134 基准超额收益结果：区间收益 vs 基准指数同期涨跌幅（缺数据一侧为 null，不造 0） */
export type BenchmarkExcessResult = {
  scope: "family" | "ledger" | "portfolio";
  ledger_id: number | null;
  portfolio_id: number | null;
  start_date: string;
  end_date: string;
  /** scope 区间收益率（%）；为 null 的原因见 range_reason */
  range_rate: number | null;
  /** 区间盈亏（元） */
  range_pnl: number | null;
  /**
   * range_rate 的分母（区间前一天净资产，元）——仅服务端组合级聚合使用；
   * 前端**禁止**拿它二次计算收益率（口径唯一，见 AGENTS.md）。
   */
  range_baseline: number | null;
  /** null=正常；否则 range_rate 为 null 的原因（no_position / no_members / baseline_missing…） */
  range_reason: string | null;
  benchmark: {
    code: string | null;
    name: string | null;
    /** 指数区间涨跌幅（%） */
    range_return: number | null;
    /** 指数实际取数首 / 末交易日（ISO），供复核「同期」是否对齐 */
    bench_start_date: string | null;
    bench_end_date: string | null;
    /** null=正常；否则降级原因（non_cn_a_holdings / unrecognized_benchmark / index_insufficient_data…） */
    reason: string | null;
  } | null;
  /** 超额（百分点）= range_rate − benchmark.range_return；任一侧为 null 则为 null */
  excess_return: number | null;
};

/** 收益归因的品种行（#2135）：区间盈亏 + 占比 */
export type PnlAttributionRow = {
  position_id: number;
  symbol: string;
  name: string | null;
  asset_type: string | null;
  ledger_id: number | null;
  /** 区间盈亏（元，已含已实现） */
  pnl: number;
  /** 占区间合计的百分比；合计为 0（没赚没赔）时为 null（不是 0%） */
  pct: number | null;
};

/** 收益归因的大类聚合行（#2135）：按 asset_type 分桶 */
export type PnlAttributionCategory = {
  asset_type: string;
  pnl: number;
  positions_count: number;
  pct: number | null;
};

/** 无价降级行（#2135）：持有但整窗无价格数据，不进合计 */
export type PnlAttributionUnpricedRow = Omit<PnlAttributionRow, "pnl" | "pct">;

export type PnlAttributionPayload = {
  scope: "family" | "ledger" | "portfolio";
  ledger_id: number | null;
  portfolio_id: number | null;
  start_date: string;
  end_date: string;
  /**
   * 区间合计盈亏（元）；整窗无可算日时为 null——诚实降级，不是 0
   *（0 会被读成「没赚没赔」，而真相是「算不了」）。
   * Σ positions[].pnl ≡ 同窗 pnl-calendar 的 month_total（构造保证）。
   */
  total_pnl: number | null;
  has_any_computable: boolean;
  /** 逐品种贡献，按 |pnl| 降序 */
  positions: PnlAttributionRow[];
  /** 大类贡献，按 |pnl| 降序 */
  categories: PnlAttributionCategory[];
  /** 持有但整窗无价的持仓——不进合计，前端折叠提示 */
  unpriced_positions: PnlAttributionUnpricedRow[];
};

/**
 * 查询区间收益 vs 基准指数超额收益（#2134 账本对齐-D）
 *
 * `start_date` / `end_date`（YYYY-MM-DD）必填；`ledger_id` 与 `portfolio_id`
 * 互斥。基准缺失（港美股持仓 / 未识别基准 / 指数数据不足）一律诚实降级 null，
 * 前端显示「--」，不显示 0。
 */
export function getBenchmarkExcess(params: {
  start_date: string;
  end_date: string;
  ledger_id?: number;
  portfolio_id?: number;
}) {
  return http.request<ApiResponse<BenchmarkExcessResult>>(
    "get",
    BASE_URL + "benchmark-excess/",
    {
      params
    }
  );
}

/**
 * 查询区间收益归因（#2135）
 *
 * 复用 pnl 引擎唯一盈亏口径（同一次 _compute_days 遍历、同一条基准推进），
 * Σ positions[].pnl 与同窗 pnl-calendar 的 month_total 由构造保证一致。
 * `ledger_id` 与 `portfolio_id` 互斥；不传两者 = 家庭级。
 */
export function getPnlAttribution(params?: {
  start_date?: string;
  end_date?: string;
  ledger_id?: number;
  portfolio_id?: number;
}) {
  return http.request<ApiResponse<PnlAttributionPayload>>(
    "get",
    BASE_URL + "pnl-attribution/",
    {
      params
    }
  );
}

/** 跨账本疑似重复组（幽灵重复扫描结果）：同一笔交易疑似出现在多个账本 */
export type GhostDuplicateGroup = {
  symbol: string;
  confirm_date: string | null;
  txn_type: string;
  amount_yuan: number;
  ledger_ids: number[];
  ledger_names: string[];
  count: number;
};

/** family 级幽灵重复扫描（#1066 / #1020）：非阻断软提示，供总览页横幅指名来源账本 */
export function getGhostDuplicates() {
  return http.request<ApiResponse<GhostDuplicateGroup[]>>(
    "get",
    BASE_URL + "ghost-duplicates/"
  );
}

/* ──────────────────────────────持仓穿透（#870 B2）──────────────────────────────
 * 后端 services/penetration.py 的出参**逐字段照抄**，不在前端二次推导比率：
 * 后端已按「已穿透 / 未穿透」两栏算好，并把「现金等价物（本质无股票敞口）」与
 * 三个真缺口分开标了 reason。**禁止在前端把 penetrated_ratio 与
 * other_schemes 的比率并列或相加**——两套分类体系不可相加（GICS 只标注港股）。
 */

/** 未穿透原因（后端 REASON_* 的字面量；reason_label 是其中文说明） */
export type PenetrationReason =
  | "cash_equivalent"
  | "fund_alloc_missing"
  | "etf_holding_missing"
  | "industry_map_missing";

/** 行业层一项（csrc / gics 主口径） */
export type PenetrationIndustry = {
  code: string;
  name: string;
  value_cny: number;
  ratio_of_total: number;
  ratio_of_penetrated: number;
  fund_count: number;
};

/** 非主口径体系（如 csrc 页面上的 gics）：带自身覆盖率，禁止与主口径并列 */
export type PenetrationOtherScheme = {
  label: string;
  covered_cny: number;
  /** 该体系只覆盖参与基金市值的多少（实测 gics 仅个位数） */
  covered_ratio_of_fund: number;
  industry_total_cny: number;
  industry_ratio_of_covered: number;
  note: string;
  industries: PenetrationIndustry[];
};

/** 个股层一项（code 为 __other__ 时name 为「其他」，是截断的聚合行） */
export type PenetrationStock = {
  code: string;
  name: string;
  value_cny: number;
  ratio_of_total: number;
  holder_fund_count: number;
};

/** 未穿透的一腿（逐条带 reason，真缺口与本质无敞口可区分） */
export type PenetrationUnpenetrated = {
  symbol: string;
  name: string;
  asset_type: string;
  value_cny: number;
  ratio_of_total: number;
  reason: PenetrationReason;
  reason_label: string;
};

export type PenetrationCoverage = {
  penetrated_cny: number;
  unpenetrated_cny: number;
  penetrated_ratio: number;
  fund_cny: number;
  direct_cny: number;
  cash_equivalent_cny: number;
  unpenetrated_fund_cny: number;
};

export type PenetrationData = {
  as_of: string;
  scheme: string;
  scheme_label: string;
  total_value_cny: number;
  coverage: PenetrationCoverage;
  industries: PenetrationIndustry[];
  /** 行业合计不足 100% 的差额＝该基金的债券/现金/其他，**不是缺失数据** */
  industry_non_equity_cny: number;
  other_schemes: Record<string, PenetrationOtherScheme>;
  stocks: PenetrationStock[];
  stocks_coverage: {
    covered_cny: number;
    fund_count_by_basis: Record<string, number>;
    report_period_by_basis: Record<string, string>;
  };
  unpenetrated: PenetrationUnpenetrated[];
  report_periods: Record<string, number>;
  /** 后端写死的口径说明，界面须原样展示而非自行改写 */
  notes: string[];
};

/**
 * 获取持仓穿透聚合（#870）。
 * @param scheme 主口径分类体系，默认 csrc（实测只有 2 只基金缺 csrc，口径最全）
 */
export function getPenetration(scheme: "csrc" | "gics" = "csrc") {
  return http.request<ApiResponse<PenetrationData>>(
    "get",
    BASE_URL + "penetration/",
    { params: { scheme } }
  );
}

/**
 * 场外基金收盘估值定格行（#2141 落库 / #2142 对照三列）。
 *
 * - `status`: `estimated`（预估定格）| `confirmed`（官方净值已对照确认，#2142）；
 * - `official_nav` / `deviation` / `deviation_pct`: 对照三列，confirmed 行有值、
 *   estimated 行为 null（**不是 0**）——徽标/提示按 null 容错，不显示脏值；
 * - `source_time` 为源端字符串原样（如 "2026-10-13 15:00"），前端不解析。
 */
export type FundValuationRow = {
  fund_code: string;
  estimated_nav: number | null;
  change_pct: number | null;
  source: string | null;
  source_time: string | null;
  status: string | null;
  official_nav?: number | null;
  deviation?: number | null;
  deviation_pct?: number | null;
};

/** 某日收盘估值定格清单（需登录；date 缺省为上海时区今日） */
export function getFundValuation(params?: {
  date?: string;
  fund_code?: string;
}) {
  return http.request<ApiResponse<FundValuationRow[]>>(
    "get",
    BASE_URL + "fund-valuation/",
    { params }
  );
}

/**
 * 账外类现金逐产品明细（持仓页「类现金」分组）。
 *
 * 货基 / 逆回购按**流水净额**记账（`position_id IS NULL`，不建持仓行），
 * 所以不会出现在持仓明细表里，但它们在**总资产里已经算过**。
 *
 * ⚠️ 这只是展示：**禁止**把这里的金额再加进页面任何合计，否则双计。
 */
export type CashLikeItem = {
  ledger_id: number | null;
  ledger_name: string;
  name: string;
  symbol: string | null;
  asset_type: string;
  asset_type_label: string;
  /** 本金净额（元） */
  net_amount: number;
  /** 累计收益（元） */
  income_amount: number;
  /** 本金 + 收益（元） */
  total_amount: number;
  txn_count: number;
};

export type CashLikeBreakdown = {
  items: CashLikeItem[];
  total_net_amount: number;
  total_income_amount: number;
  total_amount: number;
};

/** 家庭级账外类现金明细（跨账户，按「账户 + 产品」归组） */
export function getCashLikeBreakdown() {
  return http.request<ApiResponse<CashLikeBreakdown>>(
    "get",
    BASE_URL + "cash-like/"
  );
}

/* ───────────────────────清仓周期统计（#2131 · 账本对齐 A'）───────────────────────
 * 后端 services/analytics/cleared_cycles.py 的出参逐字段照抄，前端不做二次计算：
 * 盈亏由后端 FIFO 配对自算（不读流水 realized_pnl 列——存量库该列全 0），
 * 周期 = 首买 → 份额归零；数据末尾仍持有的标的未完结、不产出。
 *
 * ⚠️ `realized_pnl` / `pnl_pct` / `avg_holding_days` 为 **null = 不可算**
 * （部分配对：先卖后买 / 无买入流水），**不是 0**——展示占位「--」，
 * 且该周期不进汇总的胜率/盈亏比样本（pnl_known=false）。
 */

/** 单个清仓周期（首买 → 末卖；金额单位元，日期 ISO） */
export type ClearedCycle = {
  symbol: string;
  name: string | null;
  /** 该标的第几次清仓（同一标的可有多轮周期） */
  cycle_number: number;
  first_buy_date: string | null;
  last_sell_date: string | null;
  buy_count: number;
  sell_count: number;
  trade_count: number;
  total_buy_amount: number;
  total_sell_amount: number;
  /** 周期已实现盈亏（元）；null = 部分配对不可算，非 0 */
  realized_pnl: number | null;
  /** 盈亏率（%）= 盈亏 / 配对成本；null = 不可算 */
  pnl_pct: number | null;
  /** 份额加权平均持有天数；null = 无有效配对 */
  avg_holding_days: number | null;
  /** 周期内现金分红合计（元）；无分红为 null，不进盈亏样本 */
  dividend_total: number | null;
  /** false = 部分配对，不进汇总胜率/盈亏比样本 */
  pnl_known: boolean;
  caveats: string[];
};

/** 跨周期汇总（样本仅含 pnl_known 周期；零盈亏计样本不计胜负） */
export type ClearedCyclesSummary = {
  cycle_count: number;
  sample_count: number;
  win_count: number;
  loss_count: number;
  /** 胜率（%）；无样本为 null，非 0 */
  win_rate: number | null;
  /** 盈亏比 = 平均盈利 / 平均亏损；无亏损笔时为 null（不输出 Infinity） */
  profit_loss_ratio: number | null;
  avg_holding_days: number | null;
  /** 累计已实现盈亏（元，仅样本周期） */
  realized_pnl_total: number | null;
  total_trade_count: number;
  caveats: string[];
};

export type ClearedCyclesData = {
  cycles: ClearedCycle[];
  summary: ClearedCyclesSummary;
};

/**
 * 查询清仓周期统计（#2131，只读现算）。
 *
 * 不传 `ledger_id` = 家庭全部账户合并（产品级口径，与 XIRR/行为画像一致）；
 * `include_cash_equivalents` 默认 false（剔除货基/逆回购/cash，与复盘页 XIRR 同默认）。
 */
export function getClearedCycles(params?: {
  ledger_id?: number;
  symbol?: string;
  include_cash_equivalents?: boolean;
}) {
  return http.request<ApiResponse<ClearedCyclesData>>(
    "get",
    BASE_URL + "cleared-cycles/",
    {
      params
    }
  );
}
