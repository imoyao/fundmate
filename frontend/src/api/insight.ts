import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 一条被触发的诊断提示（#1017）。字段由后端 rules.py 注册表决定，前端不硬编码规则清单 */
export interface TipItem {
  /** 规则标识（稳定值，可用于埋点/去重） */
  code: string;
  /** 严重度：risk / warn / info */
  severity: "risk" | "warn" | "info" | string;
  title: string;
  /** 面向用户的说明，已含触发数值 */
  message: string;
  /** 为什么这条规则值得提醒（阈值与依据） */
  rationale: string;
  /** 触发时的原始数值，供复核 */
  evidence: Record<string, unknown>;
}

/** 快照摘要：用来解释「为什么一条提示都没有」 */
export interface TipSnapshot {
  holding_count: number;
  total_value_cents: number;
  penetration_ratio: number;
  latest_day: { date: string; rate_pct: number } | null;
}

export interface TipListData {
  items: TipItem[];
  count: number;
  snapshot: TipSnapshot;
}

/** 规则驱动静态诊断（家庭级，只读，不落库） */
export function getInsightTips() {
  return http.request<ApiResponse<TipListData>>("get", "/api/insight/tips/");
}
