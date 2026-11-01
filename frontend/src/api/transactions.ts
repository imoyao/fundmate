// src/api/transactions.ts
import { http } from "@/utils/http";

/** 交易流水记录（对齐 build_transaction_list 行结构；金额为元、份额为份） */
export interface TransactionRecord {
  id: number;
  /** 所属账户；账户级流水（无 symbol 的存入/税费/分红）可能为 null */
  ledger_id: number | null;
  /** 关联持仓 id；账户级流水（存入/税费等）为 null */
  position_id: number | null;
  position_name: string;
  /** 资产代码（后端 `transactions.symbol` 快照；账户级流水可能为 null） */
  symbol?: string | null;
  type: string;
  asset_type: string | null;
  trade_date: string | null;
  confirm_date: string | null;
  quantity: number;
  price: number;
  fee: number;
  amount: number;
  status: string | null;
  account_name: string;
  notes: string | null;
  source: string | null;
  /**
   * 持仓状态（`held` / `cleared` / `account`），由后端按 `ownership_status` +
   * 「持仓行是否还在」判定后下发。
   *
   * ⚠️ 不要退回「`position_id === null` 就是已清仓」：#2343 起清仓不删行，
   * 已清仓的流水 `position_id` 仍然有值，那个判据会让「已清仓」胶囊几乎永不出现。
   */
  position_state?: "held" | "cleared" | "account" | null;
  created_at: string | null;
}

/** #2137 费用拆分（元）。后端未拆分时整块为 `null`（四列全 NULL），不存在「拆了一半」。 */
export interface TransactionFeeBreakdown {
  commission: number;
  stamp_duty: number;
  transfer_fee: number;
  other_fee: number;
}

/** 展开详情里的持仓现状摘要（后端 `_position_brief`）。 */
export interface TransactionPositionBrief {
  id: number;
  name: string;
  symbol: string;
  asset_type: string | null;
  /** 当前份额（份，已从万分之一份换算） */
  quantity: number;
  /** 最近一次清仓时间（ISO）；未清仓过为 `null` */
  cleared_at: string | null;
}

/**
 * 单条流水详情（`GET /api/transactions/<id>/`）。
 *
 * **只在行被展开时请求**：这里的 `import_hash` / `plan_id` / `updated_at` / `position`
 * 列表都没有，为整页 20 行各算一遍纯属「一次性全拿到」，而绝大多数行不会被展开。
 */
export interface TransactionDetail extends TransactionRecord {
  fee_breakdown: TransactionFeeBreakdown | null;
  import_hash: string | null;
  updated_at: string | null;
  /** 来源定投计划（#2138）；`null` = 非定投 */
  plan_id: number | null;
  /** 持仓现状；`position_id` 为空或持仓行已被删（历史数据）时为 `null` */
  position: TransactionPositionBrief | null;
}

/** 汇总条单个类型桶：笔数 + 成交额（元，不含手续费） */
export interface TransactionSummaryBucket {
  count: number;
  /** `Σ amount`（元）；成交额，**不含**手续费 */
  amount: number;
}

/**
 * 交易流水汇总（`GET /api/transactions/summary/`，跟随筛选）。
 *
 * 公式在后端（设计 §四）：`净投入 = 买入 + 手续费 − 卖出 − 分红`。
 * **前端不得二次求和**——本仓已有「两套盈亏口径并存、互相矛盾」的先例，聚合数字
 * 只能有一个出处；这里也不做「用当页数据凑数」，因为当页只有 20 条。
 */
export interface TransactionSummary {
  buy: TransactionSummaryBucket;
  sell: TransactionSummaryBucket;
  dividend: TransactionSummaryBucket;
  /** `Σ fee`（元，全类型） */
  fee: number;
  /** 净投入（元）：正数＝净投入，负数＝净取出；符号必须显示 */
  net_invested: number;
}

/** 交易流水查询参数（对齐后端 list_transactions 的 query args） */
export interface TransactionListParams {
  /** 交易类型过滤（后端 txn_type 等值匹配） */
  type?: string;
  /** 时间范围：1m/3m/6m/1y/custom */
  time_range?: string;
  /** time_range=custom 时的起止日期（含边界） */
  start_date?: string;
  end_date?: string;
  status?: string;
  /** 资产类型过滤（后端经 positions 表关联） */
  asset_type?: string;
  /** 产品代码过滤（后端经 symbol_scope 匹配流水快照的真实写法） */
  symbol?: string;
  page?: number;
  per_page?: number;
}

/** 汇总条查询参数：与列表同一组筛选，但没有分页（分页与汇总无关） */
export type TransactionSummaryParams = Omit<
  TransactionListParams,
  "page" | "per_page"
>;

/** 交易流水分页响应（对齐后端信封 { data, total, page, per_page, message }） */
export interface TransactionListResponse {
  data: TransactionRecord[];
  total: number;
  page: number;
  per_page: number;
  message: string;
}

const BASE_URL = "/api/transactions";

/** 获取交易流水列表 */
export function getTransactions(params?: TransactionListParams) {
  return http.request<TransactionListResponse>("get", BASE_URL, { params });
}

/**
 * 交易流水汇总（汇总条数据源，跟随筛选）。
 *
 * 为什么不复用列表：列表是分页的（20 条/页），对它求和得到的是「这一页的汇总」——
 * 一个看起来像总计、实际只覆盖 20 行的数字。这是最坏的一种错：不报错，只骗人。
 */
export function getTransactionSummary(params?: TransactionSummaryParams) {
  return http.request<{ data: TransactionSummary; message: string }>(
    "get",
    `${BASE_URL}/summary/`,
    { params }
  );
}

/**
 * 单条流水详情（行展开详情按需取）。
 *
 * 为什么不并进列表：`import_hash` / `plan_id` / `updated_at` / `position`（当前份额、
 * 清仓时间）只有展开某一行才需要。列表为每页 20 行各算一遍是纯粹的浪费，而其中
 * 绝大多数行永远不会被展开。
 */
export function getTransactionDetail(id: number) {
  return http.request<{ data: TransactionDetail; message: string }>(
    "get",
    `${BASE_URL}/${id}/`
  );
}

/** 导出全部交易流水为 CSV（携带鉴权头，blob 下载） */
export async function exportTransactions() {
  const res = await http.request<Blob>("get", `${BASE_URL}/export/`, {
    responseType: "blob"
  });
  const url = URL.createObjectURL(res);
  const a = document.createElement("a");
  a.href = url;
  a.download = `transactions_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
