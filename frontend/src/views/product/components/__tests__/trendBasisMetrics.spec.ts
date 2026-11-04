/**
 * 走势卡口径（#2454）：净值 / 业绩（区间累计收益率）。
 *
 * 钉住四条口径：
 * 1. 业绩序列 = 窗口内归一化，**首日恒为 0**（基准是区间首日，不是成立以来）；
 * 2. 任何除零 / 非有限值都回落 0——ECharts 遇 NaN 会**默默跳过该点**（= 藏数据）；
 * 3. 收益率恒带符号显示（`+12.34%` vs `12.34%` 差一个「赚了」的确认）；
 * 4. 口径切换器第一项标签随品类变（场内「价格」/ 场外「净值」，#2171 后续纪律）。
 */
import { describe, it, expect } from "vitest";
import {
  formatReturnPercent,
  toCumulativeReturn,
  toReturnPct,
  trendBasisOptions
} from "../trendBasisMetrics";

describe("toCumulativeReturn：区间累计收益率", () => {
  it("以窗口首日为基准，首日恒为 0", () => {
    expect(toCumulativeReturn([1.0, 1.1, 1.05])).toEqual([0, 10, 5]);
  });

  it("下跌窗口给负值（不取绝对值——亏了就是亏了）", () => {
    expect(toCumulativeReturn([2.0, 1.9, 1.8])).toEqual([0, -5, -10]);
  });

  it("真实净值四位小数：保留 2 位百分比，不放大浮点噪声", () => {
    // 1.2345 → 1.2891：+4.4246...% → +4.42
    expect(toCumulativeReturn([1.2345, 1.2891])).toEqual([0, 4.42]);
  });

  it("基准为 0（理论不可能，净值恒正）→ 全 0，不产生 Infinity", () => {
    const out = toCumulativeReturn([0, 1, 2]);
    expect(out).toEqual([0, 0, 0]);
    expect(out.every(Number.isFinite)).toBe(true);
  });

  it("序列中间出现非有限值 → 该点回落 0，**不把 NaN 传给 ECharts**", () => {
    // ECharts 遇 NaN 会静默跳过该点（不报错不画）= 把数据藏了
    const out = toCumulativeReturn([1, NaN, 1.1]);
    expect(out).toEqual([0, 0, 10]);
    expect(out.every(Number.isFinite)).toBe(true);
  });

  it("空序列 → 空序列（调用方有 hasData 门禁，这里不编造）", () => {
    expect(toCumulativeReturn([])).toEqual([]);
  });

  it("长度与输入一致（ECharts category 轴按位对齐，错位=整张图漂移）", () => {
    const values = [1, 1.01, 1.02, 1.03, 1.04];
    expect(toCumulativeReturn(values)).toHaveLength(values.length);
  });
});

describe("toReturnPct：单点换算（成本线复用同一基准）", () => {
  it("与序列版同口径（同一 base 下逐点一致）", () => {
    const values = [1.0, 1.2, 0.9];
    const seq = toCumulativeReturn(values);
    expect(seq[1]).toBe(toReturnPct(values[1], values[0]));
    expect(seq[2]).toBe(toReturnPct(values[2], values[0]));
  });

  it("base 为 0 / 非有限 → 0（防 Infinity 进 option）", () => {
    expect(toReturnPct(1.5, 0)).toBe(0);
    expect(toReturnPct(NaN, 1)).toBe(0);
    expect(toReturnPct(1, Infinity)).toBe(0);
  });
});

describe("formatReturnPercent：符号纪律", () => {
  it("正数带 +，负数自带 -，零无符号", () => {
    expect(formatReturnPercent(12.345)).toBe("+12.35%");
    expect(formatReturnPercent(-3.2)).toBe("-3.20%");
    expect(formatReturnPercent(0)).toBe("0.00%");
  });

  it("轴标签用 1 位（刻度密，2 位会挤成一团）", () => {
    expect(formatReturnPercent(12.345, 1)).toBe("+12.3%");
    expect(formatReturnPercent(-3.2, 1)).toBe("-3.2%");
  });

  it("非有限值回落 0.00%（不显示 NaN%）", () => {
    expect(formatReturnPercent(NaN)).toBe("0.00%");
  });
});

describe("trendBasisOptions：口径切换器", () => {
  it("净值在前（默认口径，既有观感不变）", () => {
    expect(trendBasisOptions(false).map(o => o.value)).toEqual([
      "nav",
      "return"
    ]);
  });

  it("场外（无 OHLCV）第一项叫「净值」", () => {
    expect(trendBasisOptions(false)[0].label).toBe("净值");
  });

  it("场内第一项叫「价格」——折线画的是收盘价，叫净值会让用户对比基金净值（#2171 后续）", () => {
    expect(trendBasisOptions(true)[0].label).toBe("价格");
  });

  it("第二项恒为「业绩」", () => {
    expect(trendBasisOptions(false)[1].label).toBe("业绩");
    expect(trendBasisOptions(true)[1].label).toBe("业绩");
  });
});
