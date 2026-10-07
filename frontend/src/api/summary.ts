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
export type PnlCalendarState = "updown" | "zero" | "no_price" | "closed" | "partial";

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
 * 收益日历序列（后端 as-of 派生，**前端不做二次盈亏计算**）
 *
 * 口径：`daily_pnl` = `total_pnl` 的日差分，**不是** `net_worth` 日环比。
 * 前者对存取款免疫（建仓瞬间未实现盈亏为 0，追加投入不改变盈亏总额）；
 * 后者会被资金流污染（存入 10 万当天凭空「赚」10 万）。展示时须写明这一点。
 */
export type PnlCalendarSeries = {
  ledger_id: number | null;
  scope: "family" | "ledger";
  start_date: string;
  end_date: string;
  /** 区间内日盈亏合计（元） */
  month_total: number;
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
  days: PnlCalendarDay[];
};

/**
 * 查询收益日历（#1812）
 *
 * 与 `getSnapshots` 的区别：快照表记的是「落库当日那一刻的当前状态」，
 * 改持仓后历史**不会**更新，回填还会把今天的值贴到历史日期上；
 * 本接口从流水 + 历史价格现算，改持仓后历史自动跟着变。
 *
 * 传 `ledger_id` 返回该账户级序列；不传返回家庭级。
 */
export function getPnlCalendar(params?: {
  start_date?: string;
  end_date?: string;
  ledger_id?: number;
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
