// src/api/assets.ts
import { http } from "@/utils/http";
import type { ApiResponse, DeleteResponse } from "@/api/types";

/** 通用资产记录（对齐后端 AssetOut + _enrich_asset_dict：amount 为元，signed_amount 负债为负） */
export interface AssetRecord {
  id: number;
  user_id: number;
  major_category: string;
  minor_category: string | null;
  name: string;
  /** 金额（元，恒为正数；负债方向见 signed_amount） */
  amount: number;
  /** 带方向金额（元）：负债为负、资产为正（后端 enrich 计算字段，#1632） */
  signed_amount: number;
  currency: string;
  /** 关联账户 id（后端 AssetOut 输出，旧响应可能缺失） */
  ledger_id?: number | null;
  account_name: string | null;
  allocation: string | null;
  /** 配置目标中文标签（后端 enrich 计算字段） */
  allocation_label?: string | null;
  /** 大类中文标签（后端 enrich 计算字段） */
  type_label?: string | null;
  status: string;
  notes: string | null;
  start_date: string | null;
  end_date: string | null;
  /** 自由扩展字段（后端 JSON dict，结构随大类不同，前端按需收窄） */
  extra: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
}

/** 资产列表查询参数（对齐后端 list_assets 的 query args） */
export interface AssetListParams {
  page?: number;
  per_page?: number;
  /** 大类过滤，逗号分隔多值；传 'investment' 后端会自动展开历史细分子类（#1354） */
  major_category?: string;
  /** 小类过滤，逗号分隔多值 */
  minor_category?: string;
  /** 排除的大类，逗号分隔多值 */
  exclude?: string;
}

/** 资产分页响应（对齐后端信封 { data, total, page, per_page, message }） */
export interface AssetListResponse {
  data: AssetRecord[];
  total: number;
  page: number;
  per_page: number;
  message: string;
}

/** 创建资产入参（对齐后端 AssetCreate） */
export interface AssetCreateInput {
  major_category: string;
  minor_category?: string | null;
  name: string;
  /** 金额（元，后端校验必须大于 0） */
  amount: number;
  currency?: string;
  ledger_id?: number | null;
  account_name?: string | null;
  allocation?: string;
  status?: string;
  start_date?: string | null;
  end_date?: string | null;
  notes?: string | null;
  extra?: Record<string, unknown> | null;
}

/** 更新资产入参（PATCH，对齐后端 AssetUpdate，所有字段可选） */
export interface AssetUpdateInput {
  major_category?: string;
  minor_category?: string | null;
  name?: string;
  amount?: number;
  currency?: string;
  ledger_id?: number | null;
  account_name?: string | null;
  allocation?: string | null;
  status?: string;
  start_date?: string | null;
  end_date?: string | null;
  notes?: string | null;
  extra?: Record<string, unknown> | null;
  /**
   * 本次变动量（元，带符号；负数=还款/减少）。这是**独立业务事实**，
   * 不能由「变动后绝对值 − 当前值」反推：当前值已含后续变动，补录更早
   * 事件会平移后面整条曲线。详见 docs/design/asset-value-history-design.md §8。
   */
  delta?: number;
  effective_date?: string;
  change_note?: string;
  client_token?: string;
  change_kind?: "correction";
}

/** 资产大类汇总项（对齐后端 /summary/） */
export interface AssetSummaryItem {
  /** 分类代码（用于前端匹配） */
  code: string;
  /** 分类中文名（自带解释） */
  label: string;
  /** 汇总金额（元；负债为负） */
  value: number;
}

const BASE_URL = "/api/assets/";

export function getAssets(params?: AssetListParams) {
  return http.request<AssetListResponse>("get", BASE_URL, { params });
}

export function createAsset(data: AssetCreateInput) {
  return http.request<ApiResponse<AssetRecord>>("post", BASE_URL, { data });
}

export function updateAsset(id: number, data: AssetUpdateInput) {
  return http.request<ApiResponse<AssetRecord>>("patch", `${BASE_URL}${id}/`, {
    data
  });
}

export function deleteAsset(id: number) {
  return http.request<DeleteResponse>("delete", `${BASE_URL}${id}/`);
}

/** 获取各大类金额汇总（后端按业务顺序排列，负值即负债） */
export function getAssetsSummary() {
  return http.request<ApiResponse<AssetSummaryItem[]>>(
    "get",
    `${BASE_URL}summary/`
  );
}

/** 单资产值变动事件（D99/D100；金额单位统一为元，存储层是整数分） */
export interface AssetValueEvent {
  id: number;
  asset_id: number;
  /** 业务发生日（用户显式提供，允许早于今天） */
  effective_date: string;
  /** 录入墙钟，只做审计，不参与时点查询 */
  recorded_at: string | null;
  /** 本次变动量（元，带符号） */
  delta: number;
  /** 该事件之后的余额/估值（元）：读时折叠派生，不落库 */
  value_after: number;
  kind: string;
  notes: string | null;
}

export interface AssetValueEventsResponse {
  data: AssetValueEvent[];
  total: number;
  page: number;
  per_page: number;
  message: string;
}

export interface AssetValueAtResult {
  /** 元；valid=false 时恒为 null */
  value: number | null;
  /** start_date 未填写或查询日期早于可信下界时为 false */
  valid: boolean;
}

/** 单资产值变动时间线（按 effective_date, id 升序） */
export function getAssetValueEvents(
  id: number,
  params?: { page?: number; per_page?: number }
) {
  return http.request<AssetValueEventsResponse>(
    "get",
    `${BASE_URL}${id}/value-events/`,
    { params }
  );
}

/** 单资产时点值；缺起账日或早于下界时返回 valid=false / value=null */
export function getAssetValueAt(id: number, day: string) {
  return http.request<ApiResponse<AssetValueAtResult>>(
    "get",
    `${BASE_URL}${id}/value-at/`,
    { params: { date: day } }
  );
}
