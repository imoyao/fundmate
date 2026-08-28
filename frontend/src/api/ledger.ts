import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

export interface LedgerItem {
  id: number;
  name: string;
  ledger_type: string;
  currency: string;
  notes: string;
  default_allocation?: string;
  linked_cash_ledger_id?: number | null; // 新增
  /** 类现金产品绑定（#1137）：绑定的基金 id（「余额宝」概念，null=未绑定） */
  linked_money_fund_id?: number | null;
  /** 绑定类现金产品的基金代码（出参回显用，入参也用 code） */
  linked_money_fund_code?: string | null;
  /** 绑定类现金产品的名称（出参回显用） */
  linked_money_fund_name?: string | null;
  /** 卖出/赎回回款是否自动申购绑定的类现金产品（默认 false，需先绑定） */
  auto_purchase_money_fund?: boolean;
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
  /** 组内手动排序序号；null=按持仓金额降序默认排序（#1083） */
  display_order?: number | null;
  /** 渠道分组（用户可见分组，后端返回；列表按此分组，后端据其派生 ledger_type） */
  channel_category?: string | null;
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
  return http.request<ApiResponse<LedgerItem[]>>("get", "/api/ledgers/", {
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
  /** 渠道分组：后端据其派生 ledger_type（创建时优先传 channel_category） */
  channel_category?: string;
  notes?: string;
  default_allocation?: string;
  currency?: string;
  linked_cash_ledger_id?: number | null;
  portfolio_id?: number | null;
  fee_config?: Record<string, unknown> | null;
  sales_institution_id?: number | null;
  /** 类现金产品：基金代码（#1137，后端据其解析 funds.id 存储） */
  linked_money_fund_code?: string | null;
  /** 卖出/赎回回款是否自动申购该类现金产品（需先绑定，否则后端 400） */
  auto_purchase_money_fund?: boolean;
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
    /** 类现金产品：基金代码（#1137，null 表示解绑，解绑后开关自动关闭） */
    linked_money_fund_code?: string | null;
    /** 卖出/赎回回款是否自动申购该类现金产品（需先绑定，否则后端 400） */
    auto_purchase_money_fund?: boolean;
  }
) {
  return http.request("patch", `/api/ledgers/${id}/`, { data });
}

export function deleteLedger(id: number) {
  return http.request("delete", `/api/ledgers/${id}/`);
}

/** 组内手动排序落库（#1083）：发送该类型下的完整有序 id 列表 */
export function reorderLedgers(ledgerType: string, orderedIds: number[]) {
  return http.request("patch", "/api/ledgers/reorder/", {
    data: { ledger_type: ledgerType, ordered_ids: orderedIds }
  });
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

// ── 账本批量迁移（两段式，docs/design/ledger-merge-design.md §4）──
// preview 只读不写库（回滚 = 不提交），commit 单事务整体提交。

/** 迁移行类型：position=可交易持仓，asset=静态资产 */
export type MigrationItemKind = "position" | "asset";

/** 迁移分类：keep=直接迁移；duplicate=精确重复自动丢弃；conflict=需用户决议 */
export type MigrationClassification = "keep" | "duplicate" | "conflict";

/** 系统建议（仅 conflict 行可能非 null；merge 仅持仓行有意义） */
export type MigrationSuggestion = "keep_target" | "merge" | null;

/** 用户决议动作：持仓三选（含 merge），资产仅前两者 */
export type MigrationAction = "keep_source" | "keep_target" | "merge";

/** 持仓快照（可读值：份额为份、成本价为元） */
export interface MigrationPositionSnapshot {
  quantity: number;
  avg_price: number;
  confirm_date: string | null;
}

/** 资产快照（可读值：元） */
export interface MigrationAssetSnapshot {
  amount: number;
}

interface MigrationPreviewItemBase {
  /** 标的代码；资产行为 null */
  symbol: string | null;
  name: string;
  classification: MigrationClassification;
  suggestion: MigrationSuggestion;
  /** 不一致字段名列表（仅 conflict 行非空），如 ["quantity", "avg_price"] */
  conflict_fields: string[];
}

/** 预览明细行：持仓按 symbol 定位，数值为份额/成本价/成本日 */
export interface MigrationPositionPreviewItem extends MigrationPreviewItemBase {
  kind: "position";
  /**
   * 资产类型（如 fund/stock），前端据此切换字段术语：
   * fund 走「确认份额/确认净值/确认日期」口径，其余走「持仓数量/成本价/成本日期」。
   * 可选以兼容后端灰度期缺省，缺省按非基金处理。
   */
  asset_type?: string;
  source: MigrationPositionSnapshot;
  target: MigrationPositionSnapshot | null;
}

/**
 * 预览明细行：资产按 name+major_category+minor_category 定位。
 * major/minor_category 为 commit 决议回传所需（契约正文未列出但提交必需，
 * 后端在资产行补充输出；缺省时前端兜底空串，仅影响资产冲突决议的定位）。
 */
export interface MigrationAssetPreviewItem extends MigrationPreviewItemBase {
  kind: "asset";
  major_category?: string;
  minor_category?: string;
  source: MigrationAssetSnapshot;
  target: MigrationAssetSnapshot | null;
}

export type MigrationPreviewItem =
  MigrationPositionPreviewItem | MigrationAssetPreviewItem;

/** 守恒校验结果（迁移前后数量核对；字段随实现扩展，均为可读值） */
export interface MigrationConservation {
  source_out_positions?: number;
  target_in_positions?: number;
  source_out_assets?: number;
  target_in_assets?: number;
}

/** 账本绑定的销售机构（null=该侧未绑定机构） */
export interface MigrationInstitutionRef {
  id: number;
  name: string;
}

/** 双方销售机构绑定情况：cross_institution=true 表示双方绑定了不同机构 */
export interface MigrationInstitutionInfo {
  source: MigrationInstitutionRef | null;
  target: MigrationInstitutionRef | null;
  cross_institution: boolean;
}

/** 预览响应 data（institution 可选以兼容后端未部署新字段时的旧响应） */
export interface MigrationPreviewResult {
  items: MigrationPreviewItem[];
  conservation?: MigrationConservation;
  institution?: MigrationInstitutionInfo;
}

/** 提交决议项：持仓按 symbol 三选一；资产按三级分类键二选一（无合并语义） */
export type MigrationResolution =
  | {
      kind: "position";
      symbol: string;
      action: MigrationAction;
    }
  | {
      kind: "asset";
      name: string;
      major_category: string;
      minor_category: string;
      action: Exclude<MigrationAction, "merge">;
    };

/** 提交入参（allow_cross_institution 仅跨机构迁移且用户二次确认后携带） */
export interface MigrationCommitPayload {
  target_ledger_id: number;
  resolutions: MigrationResolution[];
  allow_cross_institution?: boolean;
}

/** 提交响应 data（各项计数与守恒结果；字段缺省时前端降级用本地预览计数展示） */
export interface MigrationCommitResult {
  position_count?: number;
  asset_count?: number;
  total?: number;
  conservation?: MigrationConservation;
}

/** 迁移预览（只读）：POST /api/ledgers/<id>/migrations/preview/ */
export function previewLedgerMigration(
  sourceLedgerId: number,
  targetLedgerId: number
) {
  return http.request<ApiResponse<MigrationPreviewResult>>(
    "post",
    `/api/ledgers/${sourceLedgerId}/migrations/preview/`,
    { data: { target_ledger_id: targetLedgerId } }
  );
}

/** 迁移提交（单事务，失败整体回滚、源数据原样）：POST /api/ledgers/<id>/migrations/commit/ */
export function commitLedgerMigration(
  sourceLedgerId: number,
  payload: MigrationCommitPayload
) {
  return http.request<ApiResponse<MigrationCommitResult>>(
    "post",
    `/api/ledgers/${sourceLedgerId}/migrations/commit/`,
    { data: payload }
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

// ── 基金E账户聚合视图（#1101）──
// 聚合家族内全部场外基金持仓（含 E 账户），供资产概览卡片与下钻页使用。
// 金额字段单位均为「分」（整数），前端展示需 /100 转「元」交给 MoneyDisplay；
// 份额字段 quantity 为 Position.quantity 原始最小单位（份×10000），前端需 /10000 转可读份额。

/** 基金聚合维度 */
export type FundAggregationDimension = "product" | "institution" | "app";

/** 聚合来源项：product 维度的 sources 与 institution/app 维度的 items 共用同一形状 */
export interface FundAggregationSource {
  ledger_id: number;
  ledger_name: string | null;
  /** 市值（分，整数） */
  market_value_cents: number;
  /** 份额（最小单位 份×10000） */
  quantity: number;
}

/** product 维度分组：按基金代码聚合 */
export interface FundAggregationProductGroup {
  symbol: string;
  name: string;
  /** 市值（分，整数） */
  market_value_cents: number;
  /** 份额合计（最小单位 份×10000） */
  quantity: number;
  sources: FundAggregationSource[];
}

/** institution 维度分组：按销售机构聚合（key 为 sales_institution_id，无关联为 "unknown"） */
export interface FundAggregationInstitutionGroup {
  key: number | "unknown";
  /** 市值（分，整数） */
  market_value_cents: number;
  items: FundAggregationSource[];
}

/** app 维度分组：按交易前端聚合（key 为 ledger.frontend_app，缺省 "self"） */
export type FundAggregationAppKey =
  "tonghuashun" | "eastmoney" | "self" | "other";

export interface FundAggregationAppGroup {
  key: FundAggregationAppKey;
  /** 市值（分，整数） */
  market_value_cents: number;
  items: FundAggregationSource[];
}

/** 基金聚合结果（GET /api/ledgers/fund-aggregation/） */
export interface FundAggregationResult {
  /** 汇总市值（分，整数） */
  total_market_value_cents: number;
  dimension: FundAggregationDimension;
  groups:
    | FundAggregationProductGroup[]
    | FundAggregationInstitutionGroup[]
    | FundAggregationAppGroup[];
}

/** 获取基金E账户聚合视图（默认按基金维度） */
export function getFundAggregation(
  dimension: FundAggregationDimension = "product"
) {
  return http.request<ApiResponse<FundAggregationResult>>(
    "get",
    "/api/ledgers/fund-aggregation/",
    { params: { dimension } }
  );
}
