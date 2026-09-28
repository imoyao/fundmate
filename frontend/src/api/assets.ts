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
