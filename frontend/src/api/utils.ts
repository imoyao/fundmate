import { http } from "@/utils/http";

/** 查询指定日期是否为交易日 */
export function checkTradingDay(date: string) {
  return http.request<any>("get", `/api/utils/trading-days/${date}/`);
}

/** 计算场外基金确认日 */
export function calcFundConfirmDate(params: {
  purchase_date: string;
  fund_type?: string;
  is_after_15?: boolean;
}) {
  return http.request<any>("get", "/api/utils/fund-confirm-dates/", { params });
}
