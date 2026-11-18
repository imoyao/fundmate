// src/views/welcome/composables/pnlFormat.ts
/**
 * 当日收益卡的数字格式化（**唯一实现**）。
 *
 * 抽出来的原因不是复用，而是「同一张卡上三种刻度必须各自统一」：
 *   - 收益率两位小数（`+0.20%`）——它是「今天赚了多少」的精确刻度；
 *   - 结构占比一位小数（`51.8%`）——它回答「大致占多少」，第二位只是噪音；
 *   - 涨跌语义只有三态（rise / fall / zero），颜色类名必须与全局一致。
 *
 * 若各组件各写一份，卡面必然出现「同一行两个百分比小数位不同」这种
 * 只有肉眼能发现的错位。故格式化只在这里写一次，组件只负责摆放。
 */

/** 涨跌语义 → 全局颜色类名（`.is-rise` / `.is-fall` / `.is-zero`） */
export const rateClass = (value: number): string =>
  value > 0 ? "is-rise" : value < 0 ? "is-fall" : "is-zero";

/** `+0.20%` / `-1.17%`：符号与数值同号，零值不带符号 */
export const signedRate = (value: number): string =>
  `${value > 0 ? "+" : value < 0 ? "-" : ""}${Math.abs(value).toFixed(2)}%`;

/**
 * 结构占比统一 1 位小数（51.8% / 12.1%）。
 *
 * 与收益率刻意不同档：收益率是精确刻度，两位有意义；占比回答「大致占多少」，
 * 第二位是噪音，还会让三列数字看起来更吵。
 */
export const pct1 = (value: number): string => `${value.toFixed(1)}%`;
