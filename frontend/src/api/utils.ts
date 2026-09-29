import { http } from "@/utils/http";

/** 交易日查询响应（对齐后端 get_trading_day） */
export interface TradingDayResponse {
  data: {
    date: string;
    /** A 股开盘日（周一至周五且非法定节假日；调休补班的周末仍为 false） */
    is_trading_day: boolean;
  };
  message: string;
}

/** 基金确认日计算响应（对齐后端 calc_fund_confirm_date） */
export interface FundConfirmDateResponse {
  data: {
    /** 实际净值日（用于拉取净值；15:00 后为顺延的下一开盘日） */
    actual_trade_date: string;
    /** T+1/T+2 确认日（用于前端展示） */
    confirm_date: string;
  };
  message: string;
}

/** 查询指定日期是否为交易日 */
export function checkTradingDay(date: string) {
  return http.request<TradingDayResponse>(
    "get",
    `/api/utils/trading-days/${date}/`
  );
}

/** 计算场外基金确认日 */
export function calcFundConfirmDate(params: {
  trade_date: string;
  fund_type?: string;
  is_after_15?: boolean;
}) {
  return http.request<FundConfirmDateResponse>(
    "get",
    "/api/utils/fund-confirm-dates/",
    { params }
  );
}
