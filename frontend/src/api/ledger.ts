import { http } from "@/utils/http";

export interface LedgerItem {
  id: number;
  name: string;
  ledger_type: string;
  currency: string;
  notes: string;
  default_allocation?: string;
  linked_cash_ledger_id?: number | null; // 新增
  /** 关联投资组合 id（账户详情页编辑弹窗使用） */
  portfolio_id?: number | null;
  /** 费率配置（证券/基金账户编辑弹窗使用） */
  fee_config?: Record<string, unknown> | null;
  /** 创建时间（ISO 字符串），用于下拉内部稳定排序 */
  created_at?: string | null;
  /** 最近使用时间：账户最后一笔交易的确认日期（ISO 字符串），用于"最近使用优先"排序 */
  last_used_at?: string | null;
  /** 关联基金销售机构 id（AMAC 名录，可选关联；null/缺省=不关联） */
  sales_institution_id?: number | null;
  /** 是否活跃：false=已归档（保留数据、仍参与收益计算，仅默认隐藏于列表） */
  is_active?: boolean;
}

/**
 * 基金销售机构（AMAC 权威名录，账户可选关联）。
 * is_common/common_sort/display_name 由后端 AMAC job 幂等策展（#1081）；
 * org_type 为 AMAC 原始 11 类，前端映射为展示标签组（独立/银行/券商/保险/其他）。
 * 字段均可选以兼容后端未部署新字段时的旧响应。
 */
export interface SalesInstitution {
  id: number;
  org_name: string;
  display_name?: string | null;
  /** AMAC 原始机构类型（11 类），如「证券公司」「独立基金销售机构」 */
  org_type?: string | null;
  /** 常用机构标志（中基协保有规模 Top10 + 5 大互联网平台 = 15 家） */
  is_common?: boolean;
  /** 常用组内排序（小者在前），非常用为 null/缺省 */
  common_sort?: number | null;
  /** 名称拼音首字母简拼（后端 AMAC job 派生），供下拉检索（如 ht=华泰证券） */
  pinyin_short?: string | null;
}

/**
 * 获取启用中的基金销售机构名录（GET /api/ledgers/sales-institutions/）。
 *
 * @param params 可选过滤参数；params.org_types 为逗号分隔（或重复传参）的原始 org_type 过滤（后端契约 #1082），缺省返回全部。
 */
export function getSalesInstitutions(params?: { org_types?: string }) {
  return http.request<{ data: SalesInstitution[] }>(
    "get",
    "/api/ledgers/sales-institutions/",
    { params }
  );
}

/** 获取用户的所有账户列表。includeArchived=true 时一并取回已归档账户。 */
export function getLedgers(includeArchived: boolean = false) {
  return http.request<any>("get", "/api/ledgers/", {
    params: { include_archived: includeArchived }
  });
}

/** 归档账户：保留全部数据、仅从日常视图隐藏（POST /api/ledgers/<id>/archive/） */
export function archiveLedger(id: number) {
  return http.request("post", `/api/ledgers/${id}/archive/`);
}

/** 激活账户：重新出现在日常视图（POST /api/ledgers/<id>/unarchive/） */
export function unarchiveLedger(id: number) {
  return http.request("post", `/api/ledgers/${id}/unarchive/`);
}

/** 创建新的账户 */
export function createLedger(data: {
  name: string;
  ledger_type?: string;
  default_allocation?: string;
  currency?: string;
  linked_cash_ledger_id?: number | null;
  portfolio_id?: number | null;
  fee_config?: Record<string, unknown> | null;
  sales_institution_id?: number | null;
}) {
  return http.request<any>("post", "/api/ledgers/", { data });
}

export function updateLedger(
  id: number,
  data: {
    name?: string;
    ledger_type?: string;
    default_allocation?: string | null;
    notes?: string;
    linked_cash_ledger_id?: number | null;
    portfolio_id?: number | null;
    fee_config?: Record<string, unknown> | null;
    sales_institution_id?: number | null;
  }
) {
  return http.request("patch", `/api/ledgers/${id}/`, { data });
}

export function deleteLedger(id: number) {
  return http.request("delete", `/api/ledgers/${id}/`);
}

export function getLedgersOverview() {
  return http.request("get", "/api/ledgers/overview/");
}

/** 删除账户，可选择同时删除持仓 */
export function deleteLedgerWithOptions(
  id: number,
  deletePositions: boolean = false
) {
  return http.request<any>("delete", `/api/ledgers/${id}/`, {
    params: { delete_positions: deletePositions }
  });
}

/** 将指定账户的持仓批量迁移到同类型目标账户 */
export interface MigrateConflict {
  symbol?: string;
  name?: string;
  major_category?: string;
  minor_category?: string;
  source?: Record<string, unknown>;
  target?: Record<string, unknown>;
}

export interface MigrateResult {
  position_count: number;
  asset_count: number;
  total: number;
  conflicts: MigrateConflict[];
}

export function migrateLedgerPositions(
  sourceLedgerId: number,
  targetLedgerId: number
) {
  return http.request<ApiResponse<MigrateResult>>(
    "post",
    `/api/ledgers/${sourceLedgerId}/migrations/`,
    {
      data: { target_ledger_id: targetLedgerId }
    }
  );
}

/** 未归置持仓归入结果 */
export interface OrphanMigrationResult {
  position_count: number;
  asset_count: number;
  transaction_count: number;
  total: number;
}

/** 未归置持仓清理结果 */
export interface OrphanCleanupResult {
  position_count: number;
  asset_count: number;
  transaction_count: number;
}

/** 将全部未归置持仓归入指定账户 */
export function migrateOrphanPositions(targetLedgerId: number) {
  return http.request<{ data: OrphanMigrationResult }>(
    "post",
    "/api/ledgers/orphan/migrations/",
    {
      data: { target_ledger_id: targetLedgerId }
    }
  );
}

/** 清理全部未归置持仓（级联删除关联交易） */
export function deleteOrphanPositions() {
  return http.request<{ data: OrphanCleanupResult }>(
    "delete",
    "/api/ledgers/orphan/"
  );
}

/** 未归置持仓明细项 */
export interface OrphanPositionItem {
  id: number;
  symbol: string;
  name: string | null;
  quantity: number;
  avg_price: number;
  market_value: number;
  pnl: number;
}

/** 未归置资产明细项 */
export interface OrphanAssetItem {
  id: number;
  name: string;
  amount: number;
  major_category: string;
}

/** 未归置交易明细项 */
export interface OrphanTransactionItem {
  id: number;
  position_name: string;
  txn_type: string;
  amount: number;
  confirm_date: string | null;
}

/** 未归置明细汇总 */
export interface OrphanDetailSummary {
  position_count: number;
  asset_count: number;
  transaction_count: number;
  total_market_value: number;
}

/** 未归置明细响应（GET /api/ledgers/orphan/detail/） */
export interface OrphanDetailResponse {
  positions: OrphanPositionItem[];
  assets: OrphanAssetItem[];
  transactions: OrphanTransactionItem[];
  summary: OrphanDetailSummary;
}

/** 未归置数据明细（孤儿持仓/资产/交易清单 + 汇总） */
export function getOrphanDetail() {
  return http.request<{ data: OrphanDetailResponse }>(
    "get",
    "/api/ledgers/orphan/detail/"
  );
}

// ── 账户详情页专用 ──

/** 获取账户概览卡片数据 */
export function getLedgerSummary(ledgerId: number) {
  return http.request("get", `/api/ledgers/${ledgerId}/summary/`);
}

/** 获取账户持仓明细（分页；search 按名称/代码模糊匹配，#982） */
export function getLedgerPositions(
  ledgerId: number,
  params: { page: number; per_page: number; search?: string }
) {
  return http.request("get", `/api/ledgers/${ledgerId}/positions/`, { params });
}

/** 获取账户交易记录（分页；search 按名称/代码模糊匹配，#982） */
export function getLedgerTransactions(
  ledgerId: number,
  params: { page: number; per_page: number; search?: string }
) {
  return http.request("get", `/api/ledgers/${ledgerId}/transactions/`, {
    params
  });
}

/** 编辑持仓 */
export function updateLedgerPosition(
  ledgerId: number,
  positionId: number,
  data: Record<string, any>
) {
  return http.request(
    "patch",
    `/api/ledgers/${ledgerId}/positions/${positionId}/`,
    { data }
  );
}

/** 删除持仓（可选级联删除交易） */
export function deleteLedgerPosition(
  ledgerId: number,
  positionId: number,
  deleteTransactions = false
) {
  return http.request(
    "delete",
    `/api/ledgers/${ledgerId}/positions/${positionId}/`,
    {
      params: { delete_transactions: deleteTransactions }
    }
  );
}

/** 编辑交易 */
export function updateLedgerTransaction(
  ledgerId: number,
  transactionId: number,
  data: Record<string, any>
) {
  return http.request(
    "patch",
    `/api/ledgers/${ledgerId}/transactions/${transactionId}/`,
    { data }
  );
}

/** 删除交易 */
export function deleteLedgerTransaction(
  ledgerId: number,
  transactionId: number
) {
  return http.request(
    "delete",
    `/api/ledgers/${ledgerId}/transactions/${transactionId}/`
  );
}
