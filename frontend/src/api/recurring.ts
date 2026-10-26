import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 定投频率（与后端 CheckConstraint 同词表，见 backend/app/domains/recurring/models.py） */
export type RecurringFrequency = "weekly" | "biweekly" | "monthly";

/** 计划状态：active 在投 / paused 暂停 / ended 已结束 */
export type RecurringStatus = "active" | "paused" | "ended";

/**
 * 定投计划（#2138）。
 *
 * 注意 `amount` 与 `invested_amount` 都是**分**（与流水同口径），展示时除 100。
 * `next_due_date` / `overdue_days` / `invested_amount` 等是后端按流水现算的派生值，
 * 前端不重算——否则两端口径一漂，用户会看到「页面说断了、账本里有流水」。
 */
export interface RecurringPlan {
  id: number;
  ledger_id: number | null;
  account_name: string | null;
  symbol: string;
  position_name: string | null;
  asset_type: string | null;
  /** 每期投入金额（分） */
  amount: number;
  frequency: RecurringFrequency;
  /** 每月第几日(1~28) 或 每周第几日(1=周一)；biweekly 恒为 null */
  day_of_period: number | null;
  start_date: string;
  end_date: string | null;
  status: RecurringStatus;
  note: string | null;
  created_at: string | null;
  updated_at: string | null;
  /** 下次应扣款日（非 active 时为 null） */
  next_due_date: string | null;
  /** 最近一期已到期的应扣款日 */
  last_due_date: string | null;
  /** 累计投入（分） */
  invested_amount: number;
  executed_count: number;
  last_executed_on: string | null;
  /** 断投天数（超过后端 7 天宽限期才算，否则 0） */
  overdue_days: number;
  is_overdue: boolean;
}

/** 新建 / 编辑入参（编辑时只传要改的字段） */
export interface RecurringPlanPayload {
  ledger_id?: number | null;
  symbol: string;
  position_name?: string | null;
  asset_type?: string | null;
  amount: number;
  frequency: RecurringFrequency;
  day_of_period?: number | null;
  start_date: string;
  end_date?: string | null;
  note?: string | null;
}

const BASE_URL = "/api/recurring-plans";

/** 计划列表；status 为空则返回全部状态 */
export function listRecurringPlans(status?: RecurringStatus) {
  return http.request<ApiResponse<RecurringPlan[]>>("get", `${BASE_URL}/`, {
    params: status ? { status } : undefined
  });
}

export function getRecurringPlan(id: number) {
  return http.request<ApiResponse<RecurringPlan>>("get", `${BASE_URL}/${id}/`);
}

export function createRecurringPlan(payload: RecurringPlanPayload) {
  return http.request<ApiResponse<RecurringPlan>>("post", `${BASE_URL}/`, {
    data: payload
  });
}

export function updateRecurringPlan(
  id: number,
  payload: Partial<RecurringPlanPayload>
) {
  return http.request<ApiResponse<RecurringPlan>>(
    "patch",
    `${BASE_URL}/${id}/`,
    { data: payload }
  );
}

/** 暂停：不再推进下次扣款日，已产生的流水不动 */
export function pauseRecurringPlan(id: number) {
  return http.request<ApiResponse<RecurringPlan>>(
    "post",
    `${BASE_URL}/${id}/pause/`
  );
}

export function resumeRecurringPlan(id: number) {
  return http.request<ApiResponse<RecurringPlan>>(
    "post",
    `${BASE_URL}/${id}/resume/`
  );
}

export function endRecurringPlan(id: number) {
  return http.request<ApiResponse<RecurringPlan>>(
    "post",
    `${BASE_URL}/${id}/end/`
  );
}
