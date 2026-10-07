// src/api/summary.ts
import { http } from "@/utils/http";
import type { ApiResponse, SummaryData } from "./types";

const BASE_URL = "/api/summary/";

/** 获取首页仪表盘聚合数据 */
export function getSummary() {
  return http.request<ApiResponse<SummaryData>>("get", BASE_URL);
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
export function getDistributions() {
  return http.request<ApiResponse<DistributionsData>>(
    "get",
    BASE_URL + "distributions/"
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
export function getPositionGroups(dimension: GroupDimension) {
  return http.request<ApiResponse<PositionGroup[]>>(
    "get",
    BASE_URL + "groups/",
    {
      params: { dimension }
    }
  );
}

/** 资产快照单条（金额元；同比百分比后端计算，无历史为 null） */
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
 * #1812 收益日历单日状态（四态，**缺数据绝不可画成 0**）
 *
 * - `updown`   有价且有持仓，当日盈亏非零
 * - `zero`     有价，当日盈亏恰为 0
 * - `no_price` 该标的整段无历史价格序列（`valuation_mode='balance'` 的银行理财/
 *   投顾/实物等，市值来自 `market_value_override` 单值非序列）
 * - `closed`   非交易日 / 未同步 / 区间首日（无前一日基准，盈亏不可算）
 */
export type PnlCalendarState = "updown" | "zero" | "no_price" | "closed";

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
