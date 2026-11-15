// frontend/src/utils/pricePrecision.ts
// 价格 / 净值位数的**唯一真源**，两个轴：
// - **展示**：`pricePrecision` / `formatPrice` / `priceAxisLabelFormatter`；
// - **录入**：`priceInputMeta`（最小报价单位 + 步进）。
//
// 两个轴方向相反，刻意不共用一个函数（见各自注释）：展示侧「宁可少给尾数」，
// 录入侧「宁可多给位数」。混成一个，任何一侧的权衡都会传染给另一侧。
//
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
 * 价格展示精度：基金 / ETF / 货币基金的最新价是净值，展示 4 位；可转债 3 位；
 * 其余 2 位。
 *
 * 可转债档（2026-11-15，issue #3120）：库里的可转债成交价是 0.0001 元整数，
 * 真实报价带 3 位（`116.036`）。此前这里归到「其余 2 位」，表格 / 持仓成本把
 * `116.036` 渲染成 `116.04` —— **展示侧的数据丢失**，与录入侧只给 2 位是同一个
 * 误判的两面。
 *
 * @param type 资产类型（`asset_type`）。未知 / 缺失按证券口径 2 位——
 *   猜成 4 位会让股票价格出现无意义的尾数，猜错的代价不对称。
 */
export const pricePrecision = (type?: string | null): number =>
  type === "fund" || type === "etf" || type === "money_fund"
    ? 4
    : type === "bond" || type === "convertible"
      ? 3
      : 2;

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

/** 价格录入的位数与步进（元） */
export interface PriceInputMeta {
  precision: number;
  step: number;
}

/**
 * 价格 / 净值**录入**精度：品种的最小报价单位（元）。
 *
 * 与 `pricePrecision`（展示）是两个轴，**不要互相顶替**：
 *
 * | 品种 | precision | step | 依据 |
 * |---|---|---|---|
 * | `fund` / `money_fund` | 4 | 0.0001 | 场外净值 |
 * | `etf` / `bond` / `convertible` | 3 | 0.001 | 场内最小价格变动 0.001 元 |
 * | `stock` | 2 | 0.01 | A 股最小价格变动 0.01 元 |
 * | 其他 / 未知 | 4 | 0.0001 | 不截断优先，见下 |
 *
 * ## 未知档为什么取 4（与展示档取 2 相反）
 *
 * `el-input-number` 的 `precision` 不是「失焦才裁剪」，而是 `handleInput →
 * verifyValue → toPrecision` **边输边舍**：录入 `116.036` 的瞬间模型值就成了
 * `116.04`，联动金额随之算错，且没有任何提示（issue #3120）。
 *
 * 所以录入侧两条路的不对称：
 * - 多给位数 ⇒ 最多是允许用户打错一个尾数，**看得见**；
 * - 少给位数 ⇒ 真实成交价被**静默改掉**，金额 / 份额 / 成本全跟着错，不可见。
 *
 * 后端 `transactions.price` 是 0.0001 元整数（`Money.yuan_to_price_units`），
 * 4 位就是它真能存下的上限，故未知品种按上限给，不猜。
 */
export function priceInputMeta(type?: string | null): PriceInputMeta {
  if (type === "fund" || type === "money_fund") {
    return { precision: 4, step: 0.0001 };
  }
  if (type === "etf" || type === "bond" || type === "convertible") {
    return { precision: 3, step: 0.001 };
  }
  if (type === "stock") {
    return { precision: 2, step: 0.01 };
  }
  return { precision: 4, step: 0.0001 };
}
