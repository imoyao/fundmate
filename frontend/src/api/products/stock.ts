// frontend/src/api/products/stock.ts
// 股票资料聚合（#2878 子域拆分；实现逐字搬自 api/products.ts，端点契约勿改）
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 股票资料聚合结果（#1969 · 详情页股票区块）。字段缺失一律为 null，前端据此降级为「—」 */
export interface StockProfileResult {
  symbol: string;
  name: string;
  market: string | null;
  /** 品类（后端 securities.type），如 stock / etf；前端不另建映射表 */
  asset_type: string;
  currency: string | null;
  /** 行业 / 板块；securities.sector 填充率有限，缺失时降级「—」而不是编造 */
  sector: string | null;
  /** 区间统计窗口（**交易日条数**，非自然日）：后端默认 60 */
  window_days: number;
  /** 行情日期 YYYY-MM-DD；无行情为 null */
  quote_date: string | null;
  /** 最新收盘价（优先前复权 adj_close）；无行情为 null */
  close: number | null;
  /** 区间最高 / 最低（**未复权原值**，与持仓页「当日最高/最低」同口径） */
  high: number | null;
  low: number | null;
  /** 区间涨跌幅(%)（窗口首日 → 最新）。null 表示首日缺失或为 0，**不是「没涨」** */
  change_pct: number | null;
  /** 前一个**有收盘价**的交易日收盘（停牌时即最后交易日收盘，与行情软件「昨收」同口径）。
      窗口内只有 1 条行情时为 null —— 没有基准就不给日涨跌 */
  prev_close: number | null;
  /** 日涨跌额 = close − prev_close；null 表示缺基准，**不是「没涨跌」** */
  change_amount: number | null;
  /** 日涨跌幅(%)（昨收 → 最新）；给「最新收盘」上色用的就是这个口径，不是区间口径 */
  day_change_pct: number | null;
  /** 实际参与统计的交易日条数；小于 window_days 说明上市/历史不足，需如实提示 */
  trading_days: number;
  /** 数据来源站点名（如「新浪财经」）；一条行情都没有时为空串 */
  source: string;
  /** 口径说明（前复权收盘价 / 未复权高低） */
  basis: string;
}

/**
 * 取股票资料聚合（详情页股票区块）。
 *
 * 只补 `/trend/` 给不出的东西（基本资料 + 区间高低）：走势曲线仍由
 * `getProductTrend` 取，本端点**不返回序列**，同页不会出现两条行情取数链路。
 * 无行情不是错误（资料照常返回、行情字段为 null），仅代码不存在才 404。
 */
export function getStockProfile(params: { symbol: string; market?: string }) {
  return http.request<ApiResponse<StockProfileResult>>(
    "get",
    "/api/products/stock-profile/",
    { params }
  );
}
