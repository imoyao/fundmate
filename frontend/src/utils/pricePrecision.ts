// frontend/src/utils/pricePrecision.ts
// 价格展示精度的**唯一真源**。
// 收口自 explore/index.vue 与 watchlist/index.vue 的重复实现（#980）。
//
// ## 为什么这里必须有「格式化」而不只是「位数」
//
// 只导出位数时，每个调用点仍要自己写 `v.toFixed(n)`，于是出现两类漂移：
// - **写死位数**：tooltip 里写 `v.toFixed(4)`，股票场景也跟着变 4 位；
// - **忘了用**：图表 y 轴压根不设 formatter，交给 echarts 默认（实测只给 1 位，
//   净值 4.8124 在轴上显示成 4.8）——这是用户实测报出来的那个 bug。
//
// 位数是数据、格式化是行为，两者都收口在这里，调用点才没有「自己再写一遍」的余地。
// 非 MoneyDisplay 的出口（echarts 轴标签 / tooltip / 标注）一律走 `formatPrice`。

/** 非有限值（null / NaN / 接口缺字段）的统一占位，避免渲染出 "NaN" / "null" */
export const PRICE_PLACEHOLDER = "—";

/**
 * 价格展示精度：基金 / ETF / 货币基金的最新价是净值，展示 4 位小数；其余 2 位。
 *
 * @param type 资产类型（`asset_type`）。未知 / 缺失按证券口径 2 位——
 *   猜成 4 位会让股票价格出现无意义的尾数，猜错的代价不对称。
 */
export const pricePrecision = (type?: string | null): number =>
  type === "fund" || type === "etf" || type === "money_fund" ? 4 : 2;

/**
 * 按资产类型格式化价格（展示用）。
 *
 * 与 `pricePrecision` 同源，保证「位数」与「渲染」不会各说一套。
 */
export const formatPrice = (
  value: number | null | undefined,
  type?: string | null
): string =>
  typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(pricePrecision(type))
    : PRICE_PLACEHOLDER;

/**
 * echarts 轴标签 / tooltip 的格式化器（按资产类型定档）。
 *
 * 轴标签走的是 canvas 渲染，`MoneyDisplay` 这类组件覆盖不到——这正是
 * 「净值在图上只剩 1 位」的成因，所以这里单独给一个可直接挂
 * `axisLabel.formatter` 的函数。
 */
export const priceAxisLabelFormatter =
  (type?: string | null) =>
  (value: number): string =>
    formatPrice(value, type);
