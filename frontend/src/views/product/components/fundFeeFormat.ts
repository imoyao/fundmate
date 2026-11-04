// frontend/src/views/product/components/fundFeeFormat.ts
/**
 * 申购 / 赎回费率文案口径（#1015 费率维度）。
 *
 * 数据来自 `GET /api/products/fund-profile/` 的 `fee_rates`，两条单位约定必须钉住：
 *
 * 1. `rate` 是**小数**（`0.015` = 1.5%），不是百分数（`FeeRatio.rate` 列注释
 *    「0.015000=1.5%」，写入侧 `_upsert_fee_ratio` 已除以 100）。格式化统一走
 *    `formatPercent`，不要在模板里再乘 100——两处各写一份就是 100 倍错误的来路。
 * 2. 区间是**半开区间**：`start_quota` / `start_day` 含下界、`end_quota` /
 *    `end_day` **不含**上界（后端 `estimate_redeem_fee` 判据 `days >= start`
 *    且 `days < end`）。所以 `[0, 7)` 要读作「不足 7 天」，写成「0~7 天」会让人
 *    以为第 7 天仍收 1.5%。
 *
 * ## 为什么收口在纯函数里
 *
 * 旧实现直接取 `rows[0]`（「阶梯取首档」），但接口**不保证顺序**（后端查询无
 * `ORDER BY`），且拿 `start_day` 当条件文案——首档 `start_day = 0` 于是渲染出
 * 「1.50%（0 天内）」这种没有意义的说明。两件事都在纯函数里钉住：**取最小档**、
 * **条件文案用区间而不是下界**。
 */

import { formatPercent } from "@/utils/format";

/** 申购费阶梯：金额区间，单位「元」；`end_quota = null` 表示无上限 */
export interface PurchaseTier {
  start_quota: number;
  end_quota: number | null;
  rate: number;
  /** 固定金额档（元/笔）；与 `rate` 互斥。大额档常是「1000 元/笔」，此时
   *  `rate` 为 0——只读 `rate` 会把它显示成「0.00%」，等于说「免费申购」。 */
  fee_amount?: number | null;
}

/** 赎回费阶梯：持有天数区间 `[start_day, end_day)`；`end_day = null` 表示无上限 */
export interface RedeemTier {
  start_day: number;
  end_day: number | null;
  rate: number;
}

export interface FeeRateText {
  /** 费率本身，如 `1.50%` */
  rate: string;
  /** 该档适用条件，如 `100 万以下` / `不足 7 天` */
  condition: string;
  /** 是否还有其它档：界面据此说明「只是最低一档」 */
  tiered: boolean;
}

/** 金额文案：万元以下用元，以上用万（去掉多余的 `.00`） */
function moneyText(yuan: number): string {
  if (Math.abs(yuan) >= 10000) return `${trimZero(yuan / 10000)} 万`;
  return `${trimZero(yuan)} 元`;
}

/** 天数文案：整年（365 的整数倍）用年，其余用天——「满 730 天」读起来不如「满 2 年」 */
function dayText(days: number): string {
  if (days > 0 && days % 365 === 0) return `${days / 365} 年`;
  return `${days} 天`;
}

function trimZero(value: number): string {
  return String(Number(value.toFixed(2)));
}

function quotaText(tier: PurchaseTier): string {
  const start = tier.start_quota ?? 0;
  const end = tier.end_quota;
  if (end == null) return start <= 0 ? "不限金额" : `${moneyText(start)}以上`;
  if (start <= 0) return `${moneyText(end)}以下`;
  return `${moneyText(start)}–${moneyText(end)}`;
}

/** 持有期条件文案：下界含、上界不含 */
function holdText(tier: RedeemTier): string {
  const start = tier.start_day ?? 0;
  const end = tier.end_day;
  if (end == null) return start <= 0 ? "不限持有期" : `满 ${dayText(start)}`;
  if (start <= 0) return `不足 ${dayText(end)}`;
  const last = end - 1;
  // 单天档（如 [7, 8)）：写成「7–7 天」会读成区间重叠
  if (last <= start) return `第 ${start} 天`;
  // 区间两端一律用「天」：一端转「年」会拼出「30–1 年」这种读不通的文案，
  // 而「7–29 天」比「7 天–29 天」短且不丢单位（单位只写一次在尾部）。
  return `${start}–${last} 天`;
}

/** 取区间下界最小的档；空列表 / 缺失返回 null（调用方显示「—」） */
function pickFirst<T>(
  rows: T[] | null | undefined,
  startOf: (r: T) => number
): T | null {
  if (!rows || !rows.length) return null;
  return rows.reduce((min, row) => (startOf(row) < startOf(min) ? row : min));
}

/** 申购费率文案：取金额下限最小的一档（金额越大费率越低） */
export function purchaseFeeText(
  rows: PurchaseTier[] | null | undefined
): FeeRateText | null {
  const list = rows ?? [];
  const tier = pickFirst(list, r => r.start_quota ?? 0);
  if (!tier) return null;
  return {
    rate: purchaseAmountText(tier),
    condition: quotaText(tier),
    tiered: list.length > 1
  };
}

/** 单档费率文案：固定金额档（`fee_amount`）优先于比例档 */
function purchaseAmountText(tier: PurchaseTier): string {
  const fixed = tier.fee_amount ?? null;
  if (fixed != null && fixed > 0) return `${moneyText(fixed)}/笔`;
  return formatPercent(tier.rate);
}

/** 赎回费率文案：取持有天数下限最小的一档（持有越久费率越低） */
export function redeemFeeText(
  rows: RedeemTier[] | null | undefined
): FeeRateText | null {
  const list = rows ?? [];
  const tier = pickFirst(list, r => r.start_day ?? 0);
  if (!tier) return null;
  return {
    rate: formatPercent(tier.rate),
    condition: holdText(tier),
    tiered: list.length > 1
  };
}

/** 赎回费阶梯明细（按持有天数升序）：折叠区里解释「为什么只显示一个数」 */
export function redeemFeeLadder(
  rows: RedeemTier[] | null | undefined
): FeeRateText[] {
  if (!rows || !rows.length) return [];
  return [...rows]
    .sort((a, b) => (a.start_day ?? 0) - (b.start_day ?? 0))
    .map(row => ({
      rate: formatPercent(row.rate),
      condition: holdText(row),
      tiered: rows.length > 1
    }));
}
