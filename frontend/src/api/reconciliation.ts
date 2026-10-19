// src/api/reconciliation.ts
// 统一对账 API（后端 reconciliation/views.py，#1232 P1）
// 信封约定与 positions/summary 一致：业务数据在 data 字段。
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 对账差异项（GET /api/reconciliation/discrepancies/ 元素） */
export interface DiscrepancyItem {
  id: number;
  domain: string;
  ledger_id: number | null;
  symbol: string;
  discrepancy_type: string; // quantity|cost|cash|orphan
  expected_value: number | null;
  actual_value: number | null;
  diff: number | null;
  status: string; // pending|cleared|ignored
  is_permanent: boolean;
  first_detected_at: string | null;
  updated_at: string | null;
}

/** 对账运行结果（POST /api/reconciliation/run/ 响应 data） */
export interface ReconciliationRunResult {
  run_id: number;
  domain: string;
  data_date: string | null;
  summary: {
    pending?: number;
    cleared?: number;
    ignored?: number;
    orphan?: number;
  };
  created: boolean;
}

/** 触发一次对账（域 B 默认；域 C 为导入后自动触发） */
export function runReconciliation(
  domain = "B"
): Promise<ApiResponse<ReconciliationRunResult>> {
  return http.post<ApiResponse<ReconciliationRunResult>, unknown>(
    "/reconciliation/run/",
    { data: { domain } }
  );
}

/** 列出活跃差异（可按域/状态筛） */
export function listDiscrepancies(params?: {
  domain?: string;
  status?: string;
}): Promise<ApiResponse<DiscrepancyItem[]>> {
  return http.get<ApiResponse<DiscrepancyItem[]>, unknown>(
    "/reconciliation/discrepancies/",
    { params }
  );
}

/** 忽略一条差异（临时或永久） */
export function ignoreDiscrepancy(
  id: number,
  payload: { permanent?: boolean; reason?: string }
): Promise<ApiResponse<{ id: number; status: string; is_permanent: boolean }>> {
  return http.post<
    ApiResponse<{ id: number; status: string; is_permanent: boolean }>,
    unknown
  >(`/reconciliation/discrepancies/${id}/ignore/`, { data: payload });
}

/** 就地补充/调整裁决请求（§5.4 / P2） */
export interface AdjustmentPayload {
  kind?: "increment" | "set";
  op_type?: string;
  discrepancy_id?: number;
  reason?: string;
  symbol?: string;
  name?: string;
  asset_type?: string;
  market?: string;
  ledger_id?: number | null;
  account_name?: string;
  quantity?: number;
  avg_price?: number;
  confirm_date?: string;
  snapshot_date?: string;
  [key: string]: unknown;
}

/** 就地补充/调整裁决响应 */
export interface AdjustmentResult {
  action: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  log_id: number;
}

/**
 * 就地补充/调整（§5.4 / P2）：工作台内直接补录，绝不跳「记一笔」。
 * - increment：补一笔缺失买卖 → process_buy_or_deposit / process_sell_or_withdraw（写流水+持仓）
 * - set：期初建仓 / 直接改数量成本 → upsert_from_holding（SET 语义，不建流水）
 */
export function applyAdjustment(
  payload: AdjustmentPayload
): Promise<ApiResponse<AdjustmentResult>> {
  return http.post<ApiResponse<AdjustmentResult>, unknown>(
    "/reconciliation/adjustments/",
    { data: payload }
  );
}

/** 账户持仓快照一致性项（GET /api/reconciliation/ledger-consistency/ 元素，#1133 §4 温柔提醒数据源） */
export interface LedgerConsistencyItem {
  ledger_id: number | null;
  symbol: string;
  name: string | null;
  /** 持仓快照日期（YYYY-MM-DD） */
  snapshot_date: string;
  /** 最近一笔流水日期（YYYY-MM-DD），无流水为 null */
  last_txn_date: string | null;
  /** 截至快照日应有份额（可读单位） */
  expected_qty: number;
  /** 当前实际份额（可读单位） */
  actual_qty: number;
  /** 差额 = 实际 − 应有（可读单位） */
  diff_qty: number;
}

/** 获取账户持仓快照一致性（只读、按需检查；不写 discrepancies 表） */
export function getLedgerConsistency(
  ledgerId?: number
): Promise<ApiResponse<{ items: LedgerConsistencyItem[] }>> {
  return http.get<
    ApiResponse<{ items: LedgerConsistencyItem[] }>,
    { ledger_id?: number }
  >(
    "/reconciliation/ledger-consistency/",
    ledgerId != null ? { params: { ledger_id: ledgerId } } : undefined
  );
}

/* ───────────────────────── 域 D：跨账本重复交易（#2151）─────────────────────────
 * 后端 `domains/reconciliation/views.py` 的 ghost-duplicates 系列端点，出参**逐字段照抄**，
 * 不在前端二次推导（与 `api/summary.ts` 的 GhostDuplicateGroup 是同一扫描的两个视角：
 * 那边是 `/api/summary/` 的只读软提示，这里是带 fingerprint 与组内明细的对账入口）。
 */

/** 组内一笔明细（`transactions[]` 元素）——「留一份、删一份」的删除目标 */
export interface GhostDuplicateTxn {
  id: number;
  ledger_id: number;
  ledger_name: string;
  /** 份额（已由后端 Money.min_unit_to_shares 转换） */
  quantity: number;
  /** 单价（已由后端转换） */
  price: number;
  amount_yuan: number;
}

/** 跨账本疑似重复组（GET /api/reconciliation/ghost-duplicates/ 的 groups 元素） */
export interface GhostDuplicateGroupItem {
  /** 稳定 id（sha256(确认日|归一身份|类型|金额|账本集合)），忽略/撤销的定位键 */
  fingerprint: string;
  symbol: string;
  /** 归一身份：同一标的的写法变体（600519 / SH600519）归为一组 */
  symbol_identity: string;
  confirm_date: string | null;
  txn_type: string;
  amount_yuan: number;
  ledger_ids: number[];
  ledger_names: string[];
  count: number;
  /** 组内明细，已按 (ledger_id, id) 升序，与「留一份、删一份」的展示顺序一致 */
  transactions: GhostDuplicateTxn[];
}

/** 域 D 列表响应（GET /api/reconciliation/ghost-duplicates/ 的 data） */
export interface GhostDuplicateList {
  groups: GhostDuplicateGroupItem[];
  /** 当前家庭已忽略的组数（供「已忽略 N 组」入口显示） */
  ignored_count: number;
}

/** 已忽略记录（GET /api/reconciliation/ghost-duplicates/ignored/ 元素，写时快照） */
export interface GhostDuplicateIgnore {
  id: number;
  fingerprint: string;
  /** 以下为忽略当时的快照，可能为 null（快照解析失败时降级） */
  symbol: string | null;
  confirm_date: string | null;
  txn_type: string | null;
  amount_yuan: number | null;
  ledger_names: string[];
  reason: string | null;
  ignored_at: string | null;
}

/** 列出跨账本疑似重复组（已减掉忽略项） */
export function listGhostDuplicates(): Promise<
  ApiResponse<GhostDuplicateList>
> {
  return http.get<ApiResponse<GhostDuplicateList>, unknown>(
    "/reconciliation/ghost-duplicates/"
  );
}

/** 列出已忽略清单（撤销入口的数据源） */
export function listGhostDuplicateIgnores(): Promise<
  ApiResponse<GhostDuplicateIgnore[]>
> {
  return http.get<ApiResponse<GhostDuplicateIgnore[]>, unknown>(
    "/reconciliation/ghost-duplicates/ignored/"
  );
}

/** 忽略一组跨账本重复（幂等：同一指纹重复忽略不报错） */
export function ignoreGhostDuplicate(
  fingerprint: string,
  payload?: { reason?: string }
): Promise<ApiResponse<{ fingerprint: string; id: number }>> {
  return http.post<ApiResponse<{ fingerprint: string; id: number }>, unknown>(
    `/reconciliation/ghost-duplicates/${fingerprint}/ignore/`,
    {
      data: payload ?? {}
    }
  );
}

/** 撤销忽略（按记录 id；清单页用，不必让 UI 去拼 64 位指纹） */
export function undoGhostDuplicateIgnoreById(
  ignoreId: number
): Promise<ApiResponse<{ deleted: boolean }>> {
  return http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/reconciliation/ghost-duplicates/ignored/${ignoreId}/`
  );
}

/** 撤销忽略（按指纹；从组列表直接撤销时用） */
export function undoGhostDuplicateIgnore(
  fingerprint: string
): Promise<ApiResponse<{ deleted: boolean }>> {
  return http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/reconciliation/ghost-duplicates/${fingerprint}/ignore/`
  );
}

// ── 域 E：红利税（#541）─────────────────────────────────────────────────────
//
// 这不是「差异」：账内没有两处数字对不上，缺的是账外那笔券商扣税。
// 后端刻意**不自动算税**（税率取决于买入批次持有期，本系统只有聚合持仓），
// 所以这里只列「哪一笔分红还没配到扣税流水 / 扣税金额看着不像红利税」，
// 由用户核对交割单后补记。

/** 域 E 一行的状态：未扣（该补记） / 已记但比例异常（该核对） */
export type DividendTaxStatus = "未扣" | "已记-比例异常";

/** 一项红利税待办（后端 `dividend_tax_service.PendingTaxItem`，粒度 = **一笔分红**） */
export interface DividendTaxPendingItem {
  symbol: string;
  name: string;
  account_name: string;
  /** 分红所属自然年 */
  year: number;
  status: DividendTaxStatus;
  /** 这笔现金分红的金额（分） */
  dividend_cents: number;
  /** 这笔分红的确认/除权日（YYYY-MM-DD） */
  dividend_on: string | null;
  /** 已配到的扣税金额（正数，分）；未扣时恒为 0 */
  tax_cents: number;
  /** 已配到的扣税日（YYYY-MM-DD）；未扣时为 null */
  tax_on: string | null;
  /** 已记税占分红的百分比；未扣时为 null */
  ratio_pct: number | null;
}

/** `GET /api/reconciliation/dividend-tax/` 的 data 信封 */
export interface DividendTaxPendingData {
  items: DividendTaxPendingItem[];
  count: number;
  /** 其中「未扣」的条数（比例异常的项不计入待补记总数） */
  pending_count: number;
  /** 待补记的分红金额合计（分） */
  total_cents: number;
  /** 本次读取顺带写入的站内通知条数（幂等，重复读为 0） */
  reminders_created?: number;
}

/** 列出红利税待办（顺带幂等写站内提醒） */
export function listDividendTaxPending(): Promise<
  ApiResponse<DividendTaxPendingData>
> {
  return http.get<ApiResponse<DividendTaxPendingData>, unknown>(
    "/reconciliation/dividend-tax/"
  );
}

/** 补记一笔红利税（幂等：同标的同一天重复提交返回既有那笔） */
export function recordDividendTax(payload: {
  symbol: string;
  /** 税额（元，正数；后端转分并存为负数） */
  amount: number;
  /** 扣税日 YYYY-MM-DD，缺省今天 */
  tax_on?: string;
  account_name?: string;
}): Promise<
  ApiResponse<{
    id: number;
    symbol: string;
    amount_cents: number;
    confirm_date: string | null;
  }>
> {
  return http.post<
    ApiResponse<{
      id: number;
      symbol: string;
      amount_cents: number;
      confirm_date: string | null;
    }>,
    unknown
  >("/reconciliation/dividend-tax/record/", { data: payload });
}
