// src/api/users.ts
import { http } from "@/utils/http";
import type { ApiResponse } from "./types";

const BASE_URL = "/api/users/";

export type RecordStats = {
  first_entry_date: string | null;
  record_days: number;
};

/** 首页欢迎语：首笔交易日期 + 累计记账天数 */
export function getRecordStats() {
  return http.request<ApiResponse<RecordStats>>("get", BASE_URL + "record-stats/");
}
