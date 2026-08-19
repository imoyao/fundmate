// frontend/src/utils/pricePrecision.ts
// 价格展示精度：基金/ETF 最新价为净值，展示 4 位小数；其余证券 2 位。
// 收口自 explore/index.vue 与 watchlist/index.vue 的重复实现（#980）。
export const pricePrecision = (type: string): number =>
  type === "fund" || type === "etf" ? 4 : 2;
