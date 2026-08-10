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

/** 查询资产快照列表（升序，含同比；可选 start_date/end_date 闭区间） */
export function getSnapshots(params?: {
  start_date?: string;
  end_date?: string;
}) {
  return http.request<ApiResponse<AssetSnapshotItem[]>>(
    "get",
    BASE_URL + "snapshots/",
    {
      params
    }
  );
}
