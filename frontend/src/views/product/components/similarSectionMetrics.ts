// frontend/src/views/product/components/similarSectionMetrics.ts
/**
 * 「相似基金」区块的展示口径（#2480）。
 *
 * 为什么单独立文件：区块的显示逻辑有三个**不许肉眼发现**的坑——
 * 1. `similarity=null` 是「上游未打分」（只给前若干名打分），与「得分 0」
 *    是两件事，必须渲染「—」；一旦 `value ?? 0` 就静默把没打分说成 0 分；
 * 2. 收益为正时要带 `+` 号（`+8.33%`），负号由数值自带，0 不带符号；
 * 3. 涨跌配色走语义 token（涨红跌绿），null 走中性色——不能因为「没有数据」
 *    就借用涨或跌的颜色。
 * 这些口径在 vitest（node 环境，无 DOM）里断言，比 e2e 更早拦住。
 */

/** 「无数据」统一占位（与全站表格一致） */
export const DASH = "—";

/** 相似度文本：null = 上游未打分，与 0 分区分展示 */
export function similarityText(value: number | null | undefined): string {
  return value == null ? DASH : value.toFixed(0);
}

/** 相似度点的 tooltip：说明 null 的真实含义，避免用户误以为故障 */
export function similarityTitle(value: number | null | undefined): string {
  return value == null ? "上游未打分" : "相似度分（0-100）";
}

/** 近 1 年收益文本：正数带 +、null 回「—」 */
export function incomeText(value: number | null | undefined): string {
  if (value == null) return DASH;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

/** 涨跌配色类（语义 token：涨红跌绿；null 走中性） */
export function incomeClass(value: number | null | undefined): string {
  if (value == null) return "flat";
  if (value > 0) return "rise";
  if (value < 0) return "fall";
  return "flat";
}
