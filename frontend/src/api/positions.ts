// src/api/positions.ts
import { http } from "@/utils/http";
import type {
  ApiResponse,
  Position,
  PositionCreate,
  PositionGroupedResponse,
  PositionListParams,
  PositionListResponse,
  PositionTransaction,
  PositionUpdate,
  TradeValidationResult
} from "./types";

const BASE_URL = "/api/positions/";

/**
 * 获取持仓分页列表。
 * 对齐后端 list_positions 分页信封：{ data: Position[], total, page, per_page, message }。
 */
export function getPositions(params?: PositionListParams) {
  return http.request<PositionListResponse>("get", BASE_URL, { params });
}

/**
 * 按账户分组获取全部持仓。
 * 对齐后端 group_by=account 返回：{ data: {ledger_id字符串: [position_dict]}, message }。
 * #2372：分组键是 **ledger_id**（String(id)，未归档持仓为 "unfiled"）而非账户名——
 * 账户名是可编辑字段，重名会并组、改名会令按名回查落空；行内仍带 account_name 快照供展示。
 * 独立函数而非给 getPositions 传 { group_by }，保证两条路径的信封类型互不混淆。
 */
export function getPositionsGroupedByAccount() {
  return http.request<PositionGroupedResponse>("get", BASE_URL, {
    params: { group_by: "account" }
  });
}

/** 新增一条持仓记录 */
export function createPosition(data: PositionCreate) {
  // 兜底默认值
  const body = {
    ...data,
    currency: data.currency || "CNY"
  };
  return http.request<ApiResponse<Position>>("post", BASE_URL, {
    data: body,
    headers: { "Content-Type": "application/json" }
  });
}

/** 更新一条持仓记录 (PATCH) */
export function updatePosition(id: number, data: PositionUpdate) {
  return http.request<ApiResponse<Position>>("patch", `${BASE_URL}${id}/`, {
    data
  });
}

/** 删除持仓，可选择同时删除关联交易 */
export function deletePosition(
  id: number,
  deleteTransactions: boolean = false
) {
  return http.request<ApiResponse<null>>("delete", `${BASE_URL}${id}/`, {
    params: { delete_transactions: deleteTransactions }
  });
}

/** 获取持仓的关联交易明细 */
export function getPositionTransactions(id: number) {
  return http.request<ApiResponse<PositionTransaction[]>>(
    "get",
    `${BASE_URL}${id}/transactions/`
  );
}

/** 按占比批量更新某产品跨账户总价（#1176）的入参 */
export type AllocateValueRequest = {
  /** 产品代码（同一产品跨账户分摊总价） */
  symbol: string;
  /** 产品维度新总价（元），必须 > 0 */
  total_value: number;
  /** 市值录入日期 YYYY-MM-DD，默认今天 */
  as_of?: string;
  /** 限定只分摊到某个账户；缺省覆盖该家庭下全部活跃账户 */
  ledger_id?: number;
};

/** 单个账户的分摊结果 */
export type AllocateValueAllocation = {
  position_id: number;
  ledger_id: number | null;
  allocated_cents: number;
  allocated_yuan: number;
  ratio: number;
};

/** 按占比批量更新总价的返回（后端 value_allocation_service） */
export type AllocateValueResult = {
  symbol: string;
  total_value_cents: number;
  total_weight_cents: number;
  as_of: string;
  allocations: AllocateValueAllocation[];
  /**
   * 上次录入市值之后是否发生过资金进出（申购/赎回/分红）（#1217）。
   * 为 true 时说明「按既有市值占比」这一分摊基数已不能反映实际持有，
   * 需要提示用户在下一个开盘日更新其他存量持仓的总价。
   */
  cash_flow_detected: boolean;
  /** 建议更新其他存量持仓的「下一个开盘日」YYYY-MM-DD；无资金进出时为 null */
  next_trading_day: string | null;
};

/**
 * 产品维度批量更新持仓总价（#1176）。
 *
 * 后端按各账户**既有市值**占比分摊：整数分计算、尾差归占比最大一笔，
 * 保证各账户分配值之和**严格等于**传入总价（不会出现一分钱对不上）。
 * 典型场景：某投顾产品跨两个账户分别投入 2 万 / 3 万，现总价 5.1 万，
 * 直接改总价即可按占比分配为 2.04 万 / 3.06 万。
 */
export function allocateValue(data: AllocateValueRequest) {
  // 注意 BASE_URL 已带尾斜杠，此处不再拼接斜杠，避免 /api/positions//xxx
  return http.request<ApiResponse<AllocateValueResult>>(
    "post",
    `${BASE_URL}allocate-value/`,
    {
      data,
      headers: { "Content-Type": "application/json" }
    }
  );
}

/** 交易规则校验（卖出数量/步长等），后端返回 { valid, message } */
export function validateTradeOrder(data: {
  symbol: string;
  market?: string;
  type: string;
  current_hold: number;
  order_qty: number;
  op_type: "buy" | "sell";
}) {
  return http.request<TradeValidationResult>("post", `${BASE_URL}validate/`, {
    data
  });
}

// ── 基金转换（设计：docs/working-notes/fund-conversion-design-2026-10-17.md） ──

/** 转换试算 / 提交的公共入参 */
export interface ConversionBaseParams {
  /** 账户 ID；缺省取转出持仓所属账户（传入则校验一致） */
  ledger_id?: number | null;
  /** 转出持仓 ID */
  out_position_id: number;
  /** 转出份额（份）；缺省或 <=0 = 全部转出（后端按持仓 4 位精确值） */
  out_quantity?: number | null;
  /** 转入基金代码（6 位裸码） */
  in_symbol: string;
  /** 指定转入金额（元）；缺省 = 净额全部转入。与 in_quantity 二选一 */
  in_amount?: number | null;
  /**
   * 指定转入份额（份，最多 2 位）；与 in_amount 二选一。
   *
   * 为什么需要它：确认单上写的是份额，按金额反算会因 4 位取整差 0.0001，
   * 对账时看着像丢了半份（#2348）。
   */
  in_quantity?: number | null;
  /**
   * 人工修正费用（元）。真实确认单的费用常与费率先算值不一致
   * （基金公司活动、钱包垫资口径），不能只读。
   */
  fee_override?: { redeem?: number | null; compensate?: number | null } | null;
  /** 交易日期 YYYY-MM-DD，缺省今天 */
  trade_date?: string | null;
}

export interface ConversionSubmitParams extends ConversionBaseParams {
  /** 退款去向：money_fund=账户绑定的类现金产品 / account_cash=退回账户现金；有退款时必填 */
  refund_mode?: "money_fund" | "account_cash" | null;
  /** 幂等键（每次提交意图一个 UUID，重发沿用同键） */
  idempotency_key: string;
}

/** 试算结果（金额单位：元；预估份额 2 位展示） */
export interface ConversionEstimateResult {
  out: {
    symbol: string;
    name: string | null;
    quantity: number;
    nav: number;
    amount: number;
    fee: number;
    fee_breakdown: { redeem: number; compensate: number };
    /** 未修正时的算法估算值（人工修正后用于提示「原估算」） */
    fee_estimated?: { redeem: number; compensate: number };
    /** 本次费用是否被人工修正 */
    fee_overridden?: boolean;
    realized_pnl_estimate: number;
  };
  in: {
    symbol: string;
    name: string | null;
    nav: number;
    amount: number;
    quantity: number;
  };
  net_amount: number;
  refund: {
    amount: number;
    options: {
      type: "money_fund" | "account_cash";
      symbol: string | null;
      name: string;
    }[];
  };
  supplement: { amount: number; required: boolean };
  trade_date: string;
  warnings: string[];
}

/** 提交结果（落库后回执） */
export interface ConversionSubmitResult {
  link_group_id: string;
  group_no: string;
  status: string;
  trade_date: string;
  confirm_date: string;
  out: ConversionEstimateResult["out"];
  in: ConversionEstimateResult["in"] & { position_id: number | null };
  refund: { amount: number; mode: string | null; txn_id: number | null };
  warnings: string[];
}

/** 基金转换试算（只读，不落库） */
export function estimateConversion(params: ConversionBaseParams) {
  return http.request<ApiResponse<ConversionEstimateResult>>(
    "post",
    `${BASE_URL}conversion/estimate/`,
    {
      data: params,
      headers: { "Content-Type": "application/json" }
    }
  );
}

/** 基金转换提交（落库：2~3 条流水同 link_group_id） */
export function submitConversion(params: ConversionSubmitParams) {
  return http.request<ApiResponse<ConversionSubmitResult>>(
    "post",
    `${BASE_URL}conversion/`,
    {
      data: params,
      headers: { "Content-Type": "application/json" }
    }
  );
}
