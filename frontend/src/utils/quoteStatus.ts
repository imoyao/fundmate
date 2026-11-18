/**
 * 行情「估 / 确认」判据（2026-11-06，自选页「当日盈亏」列）。
 *
 * ## 为什么需要它
 *
 * 自选页 `day_pnl` 列此前叫「今日估算」，一律吃实时估值价、一律挂「估」徽章。
 * 但同一个实时通道在不同时点给的是**两种性质完全不同的价**：
 *
 * | 品类 | 盘中 | 收盘 / 净值公布后 |
 * |---|---|---|
 * | 股票 / ETF / 转债 | 腾讯实时价（会跳动，是估值） | 腾讯当日收盘价（已定格，是真实值） |
 * | 场外基金 | 天天 `GSZ` 估算净值 | 官方单位净值 `NAV` / `dwjz`（真实值） |
 *
 * 用户要的是「当日盈亏」：**有今天的真实值就用真实值，没有就用估值填充**，
 * 且只有估值才标「估」。判据必须落在**数据源自带的日期/时刻**上，不能靠
 * 「现在几点了」猜——早上打开页面时行情源可能还挂着昨天的收盘价，
 * 按当前时钟判就会把昨天的价当成今天的确认值。
 *
 * ## 判据（单一出口）
 *
 * - 基金：净值日期（`jzrq` / `PDATE`）== 今天 ⇒ 官方净值已公布 ⇒ confirmed；
 * - 场内：行情日期 == 今天 **且** 行情时刻 ≥ 15:00 ⇒ 当日收盘价已定 ⇒ confirmed；
 * - 其余一律 estimated（包括静态回退价，它根本不进本函数）。
 *
 * ⚠️ 「今天」指**日历今天**（本地时区）。次日凌晨 / 非交易日，净值日期不再是
 * 今天，此时按估值处理——这是刻意的保守口径：宁可标「估」，也不把一个
 * 上一交易日的真实值冒充成「今天已确认」。交易日白天重进页面即自动转正。
 *
 * ⚠️ 本模块只回答「这份报价确认了没」，**不计算盈亏**（`views/asset/watchlist/dayPnl.ts`），
 * 也不负责取数（`realtimeDataSources.ts`）。抽成纯模块是为了能在 node 环境单测——
 * JSONP 解析器依赖 `document`，vitest 跑不了。
 */
import { formatDate } from "./date";
import { TRADING_WINDOW_END_MINUTE } from "./marketHours";

/**
 * 数据源自带的日期归一成 `YYYY-MM-DD`。
 *
 * 见过的三种形态：天天单只 `jzrq="2026-11-06"`、批量 `PDATE="2026-11-06 00:00:00"`
 * 或 `"20261106"`、腾讯时间戳 `parts[30]="20261106150000"`。
 * 只取前缀、不做 `new Date(raw)`——后者在紧凑格式与 UTC 解析上都会走偏。
 */
export function normalizeQuoteDate(raw?: string | null): string | null {
  if (!raw) return null;
  const s = String(raw).trim();
  const compact = s.match(/^(\d{4})(\d{2})(\d{2})/);
  if (compact) return `${compact[1]}-${compact[2]}-${compact[3]}`;
  const dashed = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (dashed) {
    return `${dashed[1]}-${dashed[2].padStart(2, "0")}-${dashed[3].padStart(
      2,
      "0"
    )}`;
  }
  return null;
}

/** `HH:mm` / `HHmm` / `HH:mm:ss` → 自 00:00 起的分钟数；解析不了返回 null */
export function quoteMinutes(raw?: string | null): number | null {
  if (!raw) return null;
  const s = String(raw).trim();
  const m = s.match(/^(\d{1,2}):?(\d{2})(?::\d{2})?/);
  if (!m) return null;
  const hours = Number(m[1]);
  const minutes = Number(m[2]);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null;
  if (hours > 23 || minutes > 59) return null;
  return hours * 60 + minutes;
}

/** 一份行情是否是「今日已确认价」（收盘价 / 官方净值），而非盘中估值 */
export function isConfirmedQuote(params: {
  type: "stock" | "fund";
  /** 数据源自带的价点日期（净值日期 / 行情时间戳里的日期） */
  priceDate?: string | null;
  /** 行情时刻；仅场内需要，用于判定是否已收盘 */
  priceTime?: string | null;
  /** 注入时钟便于单测 */
  now?: Date;
}): boolean {
  const date = normalizeQuoteDate(params.priceDate);
  const now = params.now ?? new Date();
  // 不是数据源标注的「今天」就不认：防止把昨天的收盘价当今天的确认值
  if (!date || date !== formatDate(now)) return false;

  if (params.type === "fund") {
    // 天天估值接口在官方净值公布后会把 jzrq / PDATE 推到当天，
    // NAV / dwjz 随之变成当日确认净值 —— 这就是「净值已更新」的唯一可靠信号。
    return true;
  }
  const minutes = quoteMinutes(params.priceTime);
  return minutes != null && minutes >= TRADING_WINDOW_END_MINUTE;
}

/**
 * 确认态时该用哪个价。
 *
 * 基金净值公布后 `GSZ`（盘中估值）可能仍停在 15:00 那个估算值，而 `NAV`
 * 已经是官方值 —— 继续用 GSZ 就会「净值更新了却仍显示估值」。
 * 官方价缺失/非正时保守回落到估值价，不显示 `—`。
 */
export function resolveQuotePrice(params: {
  estimatedPrice: number;
  officialPrice: number | null;
  confirmed: boolean;
}): number {
  const official = params.officialPrice;
  return params.confirmed &&
    official != null &&
    isFinite(official) &&
    official > 0
    ? official
    : params.estimatedPrice;
}
