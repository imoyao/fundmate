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
}

/** 获取用户的所有账户列表 */
export function getLedgers() {
  return http.request<any>("get", "/api/ledgers/");
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
export function migrateLedgerPositions(
  sourceLedgerId: number,
  targetLedgerId: number
) {
  return http.request<any>(
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

/** 获取账户持仓明细（分页） */
export function getLedgerPositions(
  ledgerId: number,
  params: { page: number; per_page: number }
) {
  return http.request("get", `/api/ledgers/${ledgerId}/positions/`, { params });
}

/** 获取账户交易记录（分页） */
export function getLedgerTransactions(
  ledgerId: number,
  params: { page: number; per_page: number }
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
