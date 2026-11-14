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
  /** 后端批量解析出的产品名（2026-11-07 第二轮）；为空时前端降级显示代码 */
  display_name?: string | null;
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
    "/api/reconciliation/run/",
    { data: { domain } }
  );
}

/** 列出活跃差异（可按域/状态筛） */
export function listDiscrepancies(params?: {
  domain?: string;
  status?: string;
}): Promise<ApiResponse<DiscrepancyItem[]>> {
  return http.get<ApiResponse<DiscrepancyItem[]>, unknown>(
    "/api/reconciliation/discrepancies/",
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
  /** 手续费（元）：仅 increment 的 buy/sell 会带；空值不传，后端按 0 计 */
  fee?: number;
  /** 成交日期（YYYY-MM-DD）：补录时与 confirm_date 同值，让流水按真实成交日排序 */
  trade_date?: string;
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
    "/api/reconciliation/adjustments/",
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
    "/api/reconciliation/ledger-consistency/",
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
  /**
   * 标的展示名（后端取 transactions.position_name，回退 positions.name）；
   * 可能为 null —— null 时前端退回代码，不许臆造名称。
   */
  display_name?: string | null;
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
  /**
   * 忽略当时的标的展示名快照（来源同组接口：transactions.position_name，
   * 回退 positions.name）；可能为 null，前端退回代码。
   */
  display_name?: string | null;
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
    "/api/reconciliation/ghost-duplicates/"
  );
}

/** 列出已忽略清单（撤销入口的数据源） */
export function listGhostDuplicateIgnores(): Promise<
  ApiResponse<GhostDuplicateIgnore[]>
> {
  return http.get<ApiResponse<GhostDuplicateIgnore[]>, unknown>(
    "/api/reconciliation/ghost-duplicates/ignored/"
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

/**
 * 域 E 一行的状态。
 *
 * `items` 里只会出现前两种（真待办）；后两种是「系统看过了、但按制度此刻不用处理」
 * 的结论，只走计数（`deferred_count` / `exempt_count`），不进待办、不发提醒。
 *
 * - `待核对`：已卖出、持股 ≤1 年、却没配到扣税流水（漏导入 / 券商未扣）；
 * - `已记-比例异常`：配到了，但金额超过分红的 20%（红利税上限）；
 * - `暂不扣税`：分红日之后还没卖出过——财税〔2015〕101 号规定派息时暂不扣缴；
 * - `依法免税`：已卖出，但持股明显超过 1 年。
 */
export type DividendTaxStatus =
  "待核对" | "已记-比例异常" | "暂不扣税" | "依法免税";

/** 一项红利税待办（后端 `dividend_tax_scan.PendingTaxItem`，粒度 = **一笔分红**） */
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
  /** 已配到的扣税金额（正数，分）；无税时为 0 */
  tax_cents: number;
  /** 已配到的扣税日（YYYY-MM-DD）；无税时为 null */
  tax_on: string | null;
  /** 已记税占分红的百分比；无税时为 null */
  ratio_pct: number | null;
}

/** `GET /api/reconciliation/dividend-tax/` 的 data 信封 */
export interface DividendTaxPendingData {
  /** 真待办：`待核对` + `已记-比例异常` */
  items: DividendTaxPendingItem[];
  count: number;
  /** 其中「待核对」的条数（比例异常的项不计入） */
  pending_count: number;
  /** 待核对的分红金额合计（分） */
  total_cents: number;
  /** 按制度暂不扣税（未卖出）的笔数 —— 不进待办，只在列表底部折叠说明 */
  deferred_count: number;
  deferred_dividend_cents: number;
  /** 依法免税（已卖出且持股超一年）的笔数 */
  exempt_count: number;
  exempt_dividend_cents: number;
  /** 本次读取顺带写入的站内通知条数（幂等，重复读为 0） */
  reminders_created?: number;
}

/** 列出红利税待办（顺带幂等写站内提醒） */
export function listDividendTaxPending(): Promise<
  ApiResponse<DividendTaxPendingData>
> {
  return http.get<ApiResponse<DividendTaxPendingData>, unknown>(
    "/api/reconciliation/dividend-tax/"
  );
}

/** 确认「这笔分红确实没有税」的身份（与待办项同源，缺一不可） */
export interface DividendTaxAckPayload {
  symbol: string;
  /** 必须回传待办项上的账户名，否则匹配不到（空串代表未归账户） */
  account_name?: string;
  /** 分红日 YYYY-MM-DD */
  dividend_on: string;
  reason?: string;
}

/**
 * 确认「这笔分红确实没有税」，之后不再提醒（幂等）。
 *
 * 为什么不记一笔 0 元扣税：0 元在税法上不是「交了 0 元税」，而是「无需纳税」。
 * 记 0 元流水会虚构一次现金流出，将来真卖出被扣税时还会抢走配对额度。
 */
export function ackDividendTax(payload: DividendTaxAckPayload): Promise<
  ApiResponse<{
    id: number;
    symbol: string;
    account_name: string;
    dividend_on: string | null;
  }>
> {
  return http.post<
    ApiResponse<{
      id: number;
      symbol: string;
      account_name: string;
      dividend_on: string | null;
    }>,
    unknown
  >("/api/reconciliation/dividend-tax/ack/", { data: payload });
}

/** 撤销确认（幂等：本来不存在也返回 `deleted=false`） */
export function revokeDividendTaxAck(
  payload: DividendTaxAckPayload
): Promise<ApiResponse<{ deleted: boolean }>> {
  // 走 POST 子路径而不是 DELETE：项目 http 封装只暴露 get/post，独立路径比给封装
  // 加方法影响面更小（`/ack/` 与 `/ack/revoke/` 在同一个后端函数里按路径分派）。
  return http.post<ApiResponse<{ deleted: boolean }>, unknown>(
    "/api/reconciliation/dividend-tax/ack/revoke/",
    { data: payload }
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
  >("/api/reconciliation/dividend-tax/record/", { data: payload });
}

// ── 域 F：悬空引用（#2866）────────────────────────────────────────────────────
// 一组交易流水仍指向已删除的持仓行。后端把修复拆成「列组 → 预览影响 → 回补 → 撤销」
// 四段，字段逐字照抄契约，前端不二次推导、不自造字段。
// 四个函数名统一以 DanglingRef 为前缀，按动作对应四个端点：
//   list… / preview…Reattach / reattach… / undo…Reattach（Reattach 只挂在写操作上，
//   读操作不带，避免 listDanglingRefReattach 这种把读说成写的名字）。

/** 目标持仓候选 / 现存持仓（契约里 live_position 与 candidates 元素同形） */
export interface DanglingRefPosition {
  id: number;
  symbol: string;
  /**
   * 持仓行上的标的名称（`positions.name`）；历史数据可能为空 —— 空时退回代码，
   * 不许臆造。下游用它把下拉 / 标题显示成「名称 · 代码」。
   */
  name?: string | null;
  quantity: number;
  ownership_status: string;
}

/** 组内一笔悬空流水（position_id 指向已不存在的持仓行） */
export interface DanglingRefTransaction {
  id: number;
  txn_type: string;
  trade_date: string | null;
  confirm_date: string | null;
  symbol: string;
  quantity: number;
  amount: number;
  position_id: number;
}

/** 一个待修复分组（GET /api/reconciliation/dangling-refs/ 的 groups 元素） */
export interface DanglingRefGroup {
  key: string;
  ledger_id: number;
  symbol: string;
  /**
   * 组内流水的标的展示名（后端取 transactions.position_name，回退 positions.name）；
   * 可能为 null —— null 时前端退回代码，不许臆造名称。
   */
  display_name?: string | null;
  txn_count: number;
  dangling_position_ids: number[];
  net_units: number;
  live_position: DanglingRefPosition | null;
  candidates: DanglingRefPosition[];
  /** 错挂组没有「导入批次」语义（它按标的归属聚合，不按导入时间），故可为 null */
  batch_id: number | null;
  batch_label: string;
  flags: string[];
  /** 后端一处判据：缺标的代码 / 无同标的现存持仓行时为 false */
  fixable: boolean;
  /** 不可回补时给出可执行的下一步，前端只显示不自行推导 */
  block_reason: string | null;
  /**
   * 错挂（`position_id` 指向**别的标的**的现存持仓）标记 + 修复方式。
   * 这三个字段只有 `/dangling-refs/mislinked/` 返回的组才有；悬空组为 undefined。
   * 有它 ⇒ 阶段判据由后端给出（`mislink`），不再走「悬空流水下一步」的派生。
   */
  mislinked?: true;
  /** remount=改挂到现存持仓（只改指针）/ rebuild=按流水新建一行再挂回 */
  fix_mode?: "remount" | "rebuild";
  /** 这些流水**现在**挂在哪几条持仓上（错误标的），供用户核对后再确认 */
  wrong_positions?: DanglingRefPosition[];
  transactions: DanglingRefTransaction[];
}

/** 批次（GET /api/reconciliation/dangling-refs/ 的 batches 元素） */
export interface DanglingRefBatch {
  id: number;
  label: string;
  txn_count: number;
  ledger_ids: number[];
  symbol_count: number;
}

/** 域 F 列表响应（GET /api/reconciliation/dangling-refs/ 的 data） */
export interface DanglingRefList {
  total: number;
  group_count: number;
  batch_count: number;
  /** 缺标的 / 缺交易日期的流水条数 */
  null_symbol: number;
  null_trade_date: number;
  /** 可直接回补的流水条数（≠ total，其余需先补全数据） */
  fixable_count: number;
  groups: DanglingRefGroup[];
  batches: DanglingRefBatch[];
}

/** 预览影响（GET /api/reconciliation/dangling-refs/preview/ 的 data） */
export interface DanglingRefPreview {
  txn_count: number;
  target_position: DanglingRefPosition | null;
  quantity_before: number;
  quantity_if_recomputed: number;
  delta: number;
  safe: boolean;
  warnings: string[];
}

/** 回补结果（POST /api/reconciliation/dangling-refs/reattach/ 的 data） */
export interface DanglingRefReattachResult {
  log_id: number;
  updated: number;
  recompute: boolean;
  quantity_before: number;
  quantity_after: number;
}

/** 撤销结果（POST /api/reconciliation/dangling-refs/undo/ 的 data） */
export interface DanglingRefUndoResult {
  restored: number;
  log_id: number;
}

/** 列出悬空引用分组、批次与汇总（只读扫描，不写库） */
export function listDanglingRefs(): Promise<ApiResponse<DanglingRefList>> {
  return http.get<ApiResponse<DanglingRefList>, unknown>(
    "/api/reconciliation/dangling-refs/"
  );
}

/** 预览把这一批流水挂到目标持仓后的份额变化（提交前必须先展示） */
export function previewDanglingRefReattach(params: {
  transaction_ids: number[];
  target_position_id: number;
}): Promise<ApiResponse<DanglingRefPreview>> {
  return http.get<
    ApiResponse<DanglingRefPreview>,
    { transaction_ids: string; target_position_id: number }
  >("/api/reconciliation/dangling-refs/preview/", {
    params: {
      transaction_ids: params.transaction_ids.join(","),
      target_position_id: params.target_position_id
    }
  });
}

/** 二次回补：把选定流水指向目标持仓（写操作，成功后凭 log_id 撤销） */
export function reattachDanglingRefs(payload: {
  transaction_ids: number[];
  target_position_id: number;
  reason?: string;
  /** 后端仍接受但会拒绝 true（自动重算改份额、不可逆）；前端不再提供该选项，故不传。 */
  recompute?: boolean;
}): Promise<ApiResponse<DanglingRefReattachResult>> {
  return http.post<ApiResponse<DanglingRefReattachResult>, unknown>(
    "/api/reconciliation/dangling-refs/reattach/",
    { data: payload }
  );
}

/** 撤销一次回补（按 log_id 还原，成功后列表由调用方重拉） */
export function undoDanglingRefReattach(
  logId: number
): Promise<ApiResponse<DanglingRefUndoResult>> {
  return http.post<ApiResponse<DanglingRefUndoResult>, unknown>(
    "/api/reconciliation/dangling-refs/undo/",
    { data: { log_id: logId } }
  );
}

// ── 域 F 第三条写路径：按流水重建持仓 ─────────────────────────────────────────
// 适用场景：持仓行被旧版「整笔卖出删行」物理删除，而买入流水还在（position_id 指向
// 已不存在的行）。既有的「回补关联」只认**现存**候选持仓，「补全信息」只改 symbol /
// trade_date，都救不了这类数据 —— 于是补录卖出会报「找不到这笔持仓」。
// 本组端点以流水为真相源建那一行：份额与成本由流水派生，不是用户手填。

/** 重建前预览（GET /api/reconciliation/dangling-refs/rebuild-preview/ 的 data） */
export interface DanglingRefRebuildPreview {
  txn_count: number;
  /** 组内唯一标的；多标的会被后端判为不可重建 */
  symbol: string | null;
  /** 标的名称（来源 transactions.position_name）；标题用它，代码只作事实行 */
  display_name: string | null;
  ledger_id: number | null;
  ledger_name: string | null;
  asset_type: string | null;
  /** 组内最早 / 最晚生效日（YYYY-MM-DD），用于让用户对照账单确认范围 */
  first_date: string | null;
  last_date: string | null;
  /** 派生出的净份额（份）与成本均价（元）——用户不必自己算 */
  net_units: number;
  avg_price: number;
  /** 后端一处判据：缺代码 / 跨账本 / 已有同标的持仓行 / 净额 ≤ 0 时为 false */
  rebuildable: boolean;
  /** 不可重建时给出可执行的下一步，前端只显示不自行推导 */
  block_reason: string | null;
  /** 口径与已知边界（不是「还原历史」，是按这组流水派生），必须原样展示 */
  warnings: string[];
}

/** 重建结果（POST /api/reconciliation/dangling-refs/rebuild/ 的 data） */
export interface DanglingRefRebuildResult {
  log_id: number;
  position_id: number;
  symbol: string;
  display_name: string | null;
  quantity: number;
  avg_price: number;
  txn_count: number;
}

/** 撤销重建结果（POST /api/reconciliation/dangling-refs/rebuild-undo/ 的 data） */
export interface DanglingRefRebuildUndoResult {
  restored: number;
  /** 1 = 期间被动过（已补卖出等），本次不撤销；数据不变但留痕 */
  skipped: number;
  log_id: number;
  skip_reason: string | null;
}

/** 预览按流水重建持仓会得到什么（只读，提交前必须先展示） */
export function previewDanglingRefRebuild(
  transactionIds: number[]
): Promise<ApiResponse<DanglingRefRebuildPreview>> {
  return http.get<
    ApiResponse<DanglingRefRebuildPreview>,
    { transaction_ids: string }
  >("/api/reconciliation/dangling-refs/rebuild-preview/", {
    params: { transaction_ids: transactionIds.join(",") }
  });
}

/** 按流水重建持仓并把这一组流水挂回去（写操作，成功后凭 log_id 撤销） */
export function rebuildDanglingRefPosition(payload: {
  transaction_ids: number[];
  reason?: string;
  /** 后端硬校验 `is True`：二次确认后才允许写入 */
  confirm: boolean;
}): Promise<ApiResponse<DanglingRefRebuildResult>> {
  return http.post<ApiResponse<DanglingRefRebuildResult>, unknown>(
    "/api/reconciliation/dangling-refs/rebuild/",
    { data: payload }
  );
}

/** 撤销一次重建（流水回到悬空、新持仓删除；期间被动过则 skipped=1 并给原因） */
export function undoDanglingRefRebuild(
  logId: number
): Promise<ApiResponse<DanglingRefRebuildUndoResult>> {
  return http.post<ApiResponse<DanglingRefRebuildUndoResult>, unknown>(
    "/api/reconciliation/dangling-refs/rebuild-undo/",
    { data: { log_id: logId } }
  );
}

// ── 域 F 重建的批量档：一次请求处理多组 ─────────────────────────────────────
// 真库 rebuild 阶段实测 90 组（2026-11-14），逐组「预览 + 写入」= 180 次往返，而组与组
// 之间用户没有任何决策点。批量**不新增写路径**：后端仍逐组跑同一份 plan、每组一条审计
// 日志，只是把往返压成 2 次（预览一次、写入一次）。业务上不可重建的组会被跳过并回报原因。

/** 批量预览里的一组（单组预览 + 组内流水 id + 账本名） */
export interface DanglingRefBatchPreviewGroup extends DanglingRefRebuildPreview {
  /** 这一组的流水 id，原样回传给写入端点 */
  transaction_ids: number[];
}

/** 批量预览（GET /api/reconciliation/dangling-refs/rebuild-batch-preview/ 的 data） */
export interface DanglingRefBatchPreview {
  group_count: number;
  rebuildable_count: number;
  blocked_count: number;
  /** 只统计可重建组的流水条数，与「将重建 N 组」同一范围 */
  txn_count: number;
  groups: DanglingRefBatchPreviewGroup[];
}

/** 批量重建结果（POST /api/reconciliation/dangling-refs/rebuild-batch/ 的 data） */
export interface DanglingRefBatchRebuildResult {
  rebuilt: Array<DanglingRefRebuildResult & { transaction_ids: number[] }>;
  /** 业务上不可重建的组：跳过并给后端原话原因，不静默 */
  skipped: Array<{
    transaction_ids: number[];
    symbol: string | null;
    reason: string;
  }>;
  log_ids: number[];
}

/** 批量撤销结果（POST /api/reconciliation/dangling-refs/rebuild-batch-undo/ 的 data） */
export interface DanglingRefBatchUndoResult {
  results: DanglingRefRebuildUndoResult[];
  restored: number;
  skipped: number;
}

/** 枚举全部悬空组并逐组给出将建出的持仓（只读，无参数） */
export function previewDanglingRefRebuildBatch(): Promise<
  ApiResponse<DanglingRefBatchPreview>
> {
  return http.get<ApiResponse<DanglingRefBatchPreview>, unknown>(
    "/api/reconciliation/dangling-refs/rebuild-batch-preview/"
  );
}

/** 批量按流水重建持仓（写操作；`confirm` 必须是 `true`，后端硬校验） */
export function rebuildDanglingRefPositionBatch(payload: {
  groups: number[][];
  reason?: string;
  confirm: boolean;
}): Promise<ApiResponse<DanglingRefBatchRebuildResult>> {
  return http.post<ApiResponse<DanglingRefBatchRebuildResult>, unknown>(
    "/api/reconciliation/dangling-refs/rebuild-batch/",
    { data: payload }
  );
}

/** 批量撤销重建：逐条回滚，期间被改过的那条 skipped=1 并给原因，不影响其余 */
export function undoDanglingRefRebuildBatch(
  logIds: number[]
): Promise<ApiResponse<DanglingRefBatchUndoResult>> {
  return http.post<ApiResponse<DanglingRefBatchUndoResult>, unknown>(
    "/api/reconciliation/dangling-refs/rebuild-batch-undo/",
    { data: { log_ids: logIds } }
  );
}

// ── 域 F 第四类：挂错标的（position_id 指向别的标的的现存持仓）──────────────────
// 既有的「回补关联」与「按流水重建持仓」都要求 position_id **悬空**（持仓行不存在），
// 而这里持仓**存在**、只是标的对不上 —— 两条修法都拒绝，数据既看不见也修不了。
// 后端检出比的是归一后的**证券代码**（不含交易场所），修法只有一条：
// 同账本有同标的持仓 ⇒ 只改指针；没有 ⇒ 按这组流水新建一行再挂回。

/** 错挂分组的列表（GET /api/reconciliation/dangling-refs/mislinked/ 的 data） */
export interface MislinkedRefList {
  total: number;
  group_count: number;
  fixable_count: number;
  /** 形状与 DanglingRefGroup 兼容，另有 mislinked / fix_mode / wrong_positions */
  groups: DanglingRefGroup[];
}

/** 改挂前预览（GET /api/reconciliation/dangling-refs/mislink-preview/ 的 data） */
export interface MislinkedRefPreview {
  txn_count: number;
  symbol: string | null;
  display_name: string | null;
  ledger_id: number | null;
  asset_type: string | null;
  /** remount=只改指针 / rebuild=按流水新建一行 */
  mode: "remount" | "rebuild";
  /** 将改挂到的持仓；null 表示会按流水新建一行 */
  target_position: DanglingRefPosition | null;
  /** 这几笔流水**现在**挂在哪几条持仓上（错误标的） */
  wrong_position_ids: number[];
  net_units: number;
  avg_price: number;
  fixable: boolean;
  block_reason: string | null;
  /** 口径与已知边界（尤其是「错误持仓份额不会自动重算」），必须原样展示 */
  warnings: string[];
}

/** 改挂结果（POST /api/reconciliation/dangling-refs/mislink/ 的 data） */
export interface MislinkedRefFixResult {
  log_id: number;
  mode: "remount" | "rebuild";
  position_id: number;
  /** 本次新建的持仓 id；remount 模式为 null */
  created_position_id: number | null;
  symbol: string;
  display_name: string | null;
  quantity: number;
  avg_price: number;
  txn_count: number;
}

/** 撤销改挂结果（POST /api/reconciliation/dangling-refs/mislink-undo/ 的 data） */
export interface MislinkedRefUndoResult {
  restored: number;
  skipped: number;
  log_id: number;
  skip_reason: string | null;
}

/** 列出「挂错标的」的流水分组（只读扫描，不写库） */
export function listMislinkedRefs(): Promise<ApiResponse<MislinkedRefList>> {
  return http.get<ApiResponse<MislinkedRefList>, unknown>(
    "/api/reconciliation/dangling-refs/mislinked/"
  );
}

/** 预览把这一批流水改挂到正确标的后会落到哪条持仓（只读） */
export function previewMislinkedRefFix(
  transactionIds: number[]
): Promise<ApiResponse<MislinkedRefPreview>> {
  return http.get<
    ApiResponse<MislinkedRefPreview>,
    { transaction_ids: string }
  >("/api/reconciliation/dangling-refs/mislink-preview/", {
    params: { transaction_ids: transactionIds.join(",") }
  });
}

/** 把一批挂错标的的流水改挂到正确标的（写操作，成功后凭 log_id 撤销） */
export function fixMislinkedRefs(payload: {
  transaction_ids: number[];
  reason?: string;
  /** 后端硬校验 `is True`：二次确认后才允许写入 */
  confirm: boolean;
}): Promise<ApiResponse<MislinkedRefFixResult>> {
  return http.post<ApiResponse<MislinkedRefFixResult>, unknown>(
    "/api/reconciliation/dangling-refs/mislink/",
    { data: payload }
  );
}

/** 撤销一次改挂（流水放回原持仓；本次新建的持仓删掉，期间被动过则 skipped=1） */
export function undoMislinkedRefFix(
  logId: number
): Promise<ApiResponse<MislinkedRefUndoResult>> {
  return http.post<ApiResponse<MislinkedRefUndoResult>, unknown>(
    "/api/reconciliation/dangling-refs/mislink-undo/",
    { data: { log_id: logId } }
  );
}

// ── 域 G：缺账本孤儿流水（#2875）─────────────────────────────────────────────
// 这些流水 ledger_id / position_id 都是 NULL：不进任何账本视图，只能全表扫描发现。
// 后端只在「同 family 下按 account_name 精确同名且唯一」时才允许回填，**只改
// ledger_id 一列**、不动份额与其它列；字段逐字照抄契约，前端不二次推导归属。
// 与域 F 的区别：域 F 需要用户选目标持仓并预览份额影响；域 G 的归属由后端
// 唯一判定，前端负责把「每条流水 → 哪个账本」逐条摊开给用户看，再二次确认。

/** 组内一条缺账本流水（GET /api/reconciliation/orphan-ledger/ 的 transactions 元素） */
export interface OrphanLedgerTransaction {
  id: number;
  txn_type: string;
  trade_date: string | null;
  confirm_date: string | null;
  symbol: string | null;
  /**
   * 流水标的展示名（后端取 transactions.position_name，回退 positions.name）；
   * 可能为 null，前端退回代码。
   */
  display_name?: string | null;
  asset_type: string | null;
  /** 账户名快照：归属判定唯一的输入 */
  account_name: string | null;
  /** 金额（元，后端已 /100）；quantity 不在响应里，本接口不碰份额 */
  amount: number;
  created_at: string | null;
  /** 后端解析出的目标账本 id；null = 无法唯一归属 */
  resolved_ledger_id: number | null;
  /** 无法归属的具体原因；可归属时为 null */
  block_reason: string | null;
}

/** 归属账本摘要 */
export interface OrphanLedgerTarget {
  id: number;
  name: string | null;
}

/** 一个归属分组（可回填组 key 为 `ledger:{id}`；不可归属的固定为 `blocked`） */
export interface OrphanLedgerGroup {
  key: string;
  resolved_ledger: OrphanLedgerTarget | null;
  txn_count: number;
  /** 组级原因：组内原因不一致时是概括说明，逐条真实原因看 transactions */
  block_reason: string | null;
  batch_id: number;
  batch_label: string;
  transactions: OrphanLedgerTransaction[];
}

/** 导入批次（按 created_at 相邻间隔 > 600 秒切分） */
export interface OrphanLedgerBatch {
  id: number;
  label: string;
  txn_count: number;
}

/** 域 G 列表响应（GET /api/reconciliation/orphan-ledger/ 的 data） */
export interface OrphanLedgerList {
  total: number;
  /** 可唯一归属、可回填的流水条数 */
  fixable_count: number;
  blocked_count: number;
  batch_count: number;
  groups: OrphanLedgerGroup[];
  batches: OrphanLedgerBatch[];
}

/** 回填结果（POST /api/reconciliation/orphan-ledger/backfill/ 的 data） */
export interface OrphanLedgerBackfillResult {
  log_id: number;
  updated: number;
  ledgers: Array<{ id: number; name: string | null; count: number }>;
}

/** 撤销结果（POST /api/reconciliation/orphan-ledger/undo/ 的 data） */
export interface OrphanLedgerUndoResult {
  restored: number;
  log_id: number;
}

/** 列出缺账本孤儿流水的分组与批次（只读扫描，不写库） */
export function listOrphanLedgers(): Promise<ApiResponse<OrphanLedgerList>> {
  return http.get<ApiResponse<OrphanLedgerList>, unknown>(
    "/api/reconciliation/orphan-ledger/"
  );
}

/** 按用户显式给出的流水 id 回填账本（写操作，成功后凭 log_id 撤销） */
export function backfillOrphanLedgers(payload: {
  transaction_ids: number[];
  reason?: string;
}): Promise<ApiResponse<OrphanLedgerBackfillResult>> {
  return http.post<ApiResponse<OrphanLedgerBackfillResult>, unknown>(
    "/api/reconciliation/orphan-ledger/backfill/",
    { data: payload }
  );
}

/** 撤销一次回填（按 log_id 还原，成功后列表由调用方重拉） */
export function undoOrphanLedgerBackfill(
  logId: number
): Promise<ApiResponse<OrphanLedgerUndoResult>> {
  return http.post<ApiResponse<OrphanLedgerUndoResult>, unknown>(
    "/api/reconciliation/orphan-ledger/undo/",
    { data: { log_id: logId } }
  );
}

// ── 域 F 续：数据缺失流水的「补全信息 / 显式删除」（#2866）──────────────────
// 532 条 blocked 数据在 #2926 里只能看、不能动。这两条写路径都要求用户显式动作：
// 补全只填空值（symbol / trade_date），删除要求输入「删除」二字二次确认。
// 后端在写入前会再次校验「仍悬空 + 同一 family」，并写 adjustment_logs 供撤销。
// ⚠️ 路径必须带 /api 前缀：src/api/__tests__/reconciliationApiPrefix.spec.ts 会读源码
// 钉死这一点（Vite 只代理 /api，漏前缀会拿到 index.html，页面静默显示全 0）。

/** 补全前预览（GET /enrich-preview/ 的 data） */
export interface DanglingRefEnrichPreview {
  txn_count: number;
  fill_symbol_count: number;
  fill_date_count: number;
  unchanged_count: number;
  symbol: string | null;
  trade_date: string | null;
  candidate_positions: Array<{
    id: number;
    symbol: string;
    ledger_id: number;
    quantity: number;
    ownership_status: string;
  }>;
  changes: Array<{
    id: number;
    symbol_before: string | null;
    symbol_after: string | null;
    trade_date_before: string | null;
    trade_date_after: string | null;
    asset_type: string | null;
  }>;
  warnings: string[];
}

/** 补全结果（POST /enrich/ 的 data） */
export interface DanglingRefEnrichResult {
  log_id: number;
  updated: number;
  skipped: number;
  symbol: string | null;
  trade_date: string | null;
}

/** 删除前预览（GET /delete-preview/ 的 data），数量是「份」、金额是「元」 */
export interface DanglingRefDeletePreview {
  txn_count: number;
  transactions: Array<{
    id: number;
    txn_type: string;
    trade_date: string | null;
    symbol: string | null;
    quantity: number;
    amount: number;
    position_id: number;
    realized_pnl: number;
    is_income: boolean | null;
  }>;
  snapshot_columns: number;
  total_amount: number;
  warnings: string[];
}

/** 删除结果（POST /delete/ 的 data） */
export interface DanglingRefDeleteResult {
  log_id: number;
  deleted: number;
  total_amount: number;
  confirm_phrase: string;
}

/** 补全 / 删除的撤销结果 */
export interface RemediationUndoResult {
  restored: number;
  skipped: number;
  log_id: number;
}

/** 补全前预览：只算不改，并给出补完后可能可挂回的现存持仓 */
export function previewDanglingRefEnrich(params: {
  transaction_ids: number[];
  symbol?: string;
  trade_date?: string;
}): Promise<ApiResponse<DanglingRefEnrichPreview>> {
  return http.get<
    ApiResponse<DanglingRefEnrichPreview>,
    { transaction_ids: string; symbol?: string; trade_date?: string }
  >("/api/reconciliation/dangling-refs/enrich-preview/", {
    params: {
      transaction_ids: params.transaction_ids.join(","),
      symbol: params.symbol,
      trade_date: params.trade_date
    }
  });
}

/** 补全空字段（写操作，成功后凭 log_id 撤销） */
export function enrichDanglingRefs(payload: {
  transaction_ids: number[];
  symbol?: string;
  trade_date?: string;
  reason?: string;
  confirm: boolean;
}): Promise<ApiResponse<DanglingRefEnrichResult>> {
  return http.post<ApiResponse<DanglingRefEnrichResult>, unknown>(
    "/api/reconciliation/dangling-refs/enrich/",
    { data: payload }
  );
}

/** 撤销一次补全（幂等，列表由调用方重拉） */
export function undoDanglingRefEnrich(
  logId: number
): Promise<ApiResponse<RemediationUndoResult>> {
  return http.post<ApiResponse<RemediationUndoResult>, unknown>(
    "/api/reconciliation/dangling-refs/enrich-undo/",
    { data: { log_id: logId } }
  );
}

/** 删除前预览：只算不删，展示将删除的记录与完整快照列数 */
export function previewDanglingRefDelete(params: {
  transaction_ids: number[];
}): Promise<ApiResponse<DanglingRefDeletePreview>> {
  return http.get<
    ApiResponse<DanglingRefDeletePreview>,
    { transaction_ids: string }
  >("/api/reconciliation/dangling-refs/delete-preview/", {
    params: { transaction_ids: params.transaction_ids.join(",") }
  });
}

/** 显式删除（后端硬校验 confirm_phrase === "删除"，成功后凭 log_id 撤销） */
export function deleteDanglingRefs(payload: {
  transaction_ids: number[];
  reason?: string;
  confirm: boolean;
  confirm_phrase: string;
}): Promise<ApiResponse<DanglingRefDeleteResult>> {
  return http.post<ApiResponse<DanglingRefDeleteResult>, unknown>(
    "/api/reconciliation/dangling-refs/delete/",
    { data: payload }
  );
}

/** 撤销一次删除（按完整行快照恢复，列表由调用方重拉） */
export function undoDanglingRefDelete(
  logId: number
): Promise<ApiResponse<RemediationUndoResult>> {
  return http.post<ApiResponse<RemediationUndoResult>, unknown>(
    "/api/reconciliation/dangling-refs/delete-undo/",
    { data: { log_id: logId } }
  );
}
