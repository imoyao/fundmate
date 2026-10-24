// frontend/src/views/product/components/trendBasisMetrics.ts
/**
 * 走势卡「口径」维度（#2454）：y 轴画**什么**——绝对净值/价格，还是区间累计收益率。
 *
 * 与 `trendViewMetrics`（图表类型维度：K 线/折线）**正交**：
 * - 口径（本文件）：净值线答「现在多少钱」，业绩线答「这段时间赚了多少」；
 * - 视图（trendViewMetrics）：用什么画——折线还是 K 线。
 *
 * 两个维度合成「实际在画什么」时守一条纪律：**K 线只属于净值口径**。
 * K 线画的是 OHLC 价格，没有「收益率 K 线」这种东西；给一个点了没反应的
 * 「业绩」选项就是假可操作性（#2453 同款教训）。由组件把
 * `basis === 'nav' && effectiveUseCandle(...)` 合取成 useCandle 保证。
 *
 * 用户原话（#2454）：「走势图现在只有净值走势，没有收益走势……确实应该是业绩走势」。
 */

export type TrendBasis = "nav" | "return";

export interface TrendBasisOption {
  label: string;
  value: TrendBasis;
}

/**
 * 口径切换器选项：第一项标签**随品类变**。
 *
 * 场内画的是收盘价、场外才是净值——名字不能都叫「净值」，否则场内用户会拿它
 * 去对比基金净值（#2171 后续同款纪律，与 series 名一致）。
 */
export function trendBasisOptions(isCandle: boolean): TrendBasisOption[] {
  return [
    { label: isCandle ? "价格" : "净值", value: "nav" },
    { label: "业绩", value: "return" }
  ];
}

/**
 * 单点收益率（%）：`(value - base) / base × 100`，保留 2 位。
 *
 * ⚠️ 非有限值一律回落 `0`：ECharts 遇到 `NaN` / `Infinity` 会**默默跳过该点**
 * （不报错、不画），等于把数据藏了——`trendMarkerMetrics` 里 markerSize 的
 * 「分母为 0 不产生 NaN」是同款教训。base 为 0（理论不可能，净值恒正）同样防。
 */
export function toReturnPct(value: number, base: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(base) || base === 0) return 0;
  const pct = ((value - base) / base) * 100;
  return Number.isFinite(pct) ? +pct.toFixed(2) : 0;
}

/**
 * 区间累计收益率序列（%）：以**窗口首日**为基准，首日恒为 0。
 *
 * 为什么在前端算而不是让后端给：这是对已有序列的**纯派生**（不跨表、不聚合
 * 明细），切换区间时无需重新请求——与 `movingAverage` 同源的理由（数据策略
 * 约束针对的是跨表聚合，不是单序列滑窗）。
 *
 * 为什么基准是窗口首日而不是成立以来：用户问的是「**这段**时间赚了多少」。
 * 成立以来收益是业绩卡的口径，同页不造第二个数字（#2171 决策）。
 */
export function toCumulativeReturn(values: number[]): number[] {
  const base = values.length > 0 ? values[0] : NaN;
  if (!Number.isFinite(base) || base === 0) {
    return values.map(() => 0);
  }
  return values.map(v => toReturnPct(v, base));
}

/**
 * 收益率显示：恒带符号（`+`/空负号即 `-`），2 位小数。
 *
 * 带符号是必须的：`12.34%` 与 `+12.34%` 在轴标签上差一个「这是赚了」的确认，
 * 而 `0.00%` 无符号天然表达「不赚不亏」。
 */
export function formatReturnPercent(value: number, digits = 2): string {
  const safe = Number.isFinite(value) ? value : 0;
  const sign = safe > 0 ? "+" : "";
  return `${sign}${safe.toFixed(digits)}%`;
}
