/**
 * 走势列 `title` 口径（#2651）。
 *
 * ## 这个文件钉什么
 *
 * 1. **无数据显示 `--` 时也必须带 `title`**——这是本卡的全部意义。原来的早退分支
 *    直接吐一个裸 `--`，场外基金那句「无盘中估值分时」根本走不到，#2640 的验收
 *    「hover 有说明」因此在真机上永远看不到。
 * 2. **场外无数据 ≠ 场内无数据**——前者是「没有分时源」（产品事实），后者是
 *    「数据没回填」（可修复），说成同一句话会把用户引向错误结论。
 * 3. **场外有日线时文案不许变**——`场外基金无盘中估值分时，显示近 60 日净值走势`
 *    是 #2640 已验收的文案，本卡只补空缺分支。
 * 4. **分时点数不足与没有分时分流**——刚开盘 1 个点不是「无分时」，否则开盘头几分钟
 *    全场都显示「场外基金…」，比空白更误导。
 *
 * ⚠️ 为什么不直接测渲染器：vitest 是 node 环境（无 DOM），`columnRenderers.tsx`
 * 会一路 import `.vue` 组件（同 `dayPnl.spec.ts` 的说明）。渲染器只负责把点数传进来，
 * 文案判据全部收敛在这个纯函数里。
 */
import { describe, expect, it } from "vitest";

import { resolveSparklineTitle } from "../sparklineTitle";

const OTC_WITH_TREND = "场外基金无盘中估值分时，显示近 60 日净值走势";

describe("resolveSparklineTitle：有数据时说明口径", () => {
  it("分时 ≥2 点 → 当日分时", () => {
    expect(
      resolveSparklineTitle({
        isOtc: false,
        intradayPoints: 30,
        trendPoints: 60
      })
    ).toBe("当日分时走势（盘中实时）");
  });

  it("有日线无分时：场外仍是 #2640 已验收的文案（不许改）", () => {
    expect(
      resolveSparklineTitle({ isOtc: true, intradayPoints: 0, trendPoints: 36 })
    ).toBe(OTC_WITH_TREND);
  });

  it("有日线无分时：场内说明是收盘价", () => {
    expect(
      resolveSparklineTitle({
        isOtc: false,
        intradayPoints: 0,
        trendPoints: 36
      })
    ).toBe("近 60 日收盘价走势");
  });

  it("分时只有 1 点但有日线 → 回落日线口径（不谎称有分时）", () => {
    expect(
      resolveSparklineTitle({
        isOtc: false,
        intradayPoints: 1,
        trendPoints: 60
      })
    ).toBe("近 60 日收盘价走势");
  });
});

describe("resolveSparklineTitle：无数据时必须解释为什么是 --", () => {
  it("场外无日线：title 非空，且同时含「场外基金」与「无」（#2651 验收 1）", () => {
    const title = resolveSparklineTitle({
      isOtc: true,
      intradayPoints: 0,
      trendPoints: 0
    });
    expect(title).not.toBe("");
    expect(title).toContain("场外基金");
    expect(title).toContain("无");
    // 不能复用「显示近 60 日净值走势」——那会把「没有线」说成「有线」
    expect(title).not.toContain("显示近 60 日");
  });

  it("场外无日线 ≠ 场内无日线，且场内文案不含「场外基金」（#2651 验收 3）", () => {
    const otc = resolveSparklineTitle({
      isOtc: true,
      intradayPoints: 0,
      trendPoints: 0
    });
    const market = resolveSparklineTitle({
      isOtc: false,
      intradayPoints: 0,
      trendPoints: 0
    });
    expect(market).not.toBe(otc);
    expect(market).not.toContain("场外基金");
    expect(market).toBe("暂无走势数据");
  });

  it("分时 1 点且无日线 → 说「刚开盘」，不说「无分时源」", () => {
    const title = resolveSparklineTitle({
      isOtc: false,
      intradayPoints: 1,
      trendPoints: 0
    });
    expect(title).toContain("分时");
    expect(title).toContain("暂无数据");
    expect(title).not.toBe("暂无走势数据");
  });

  it("点数缺省（undefined / null）按 0 处理，不抛错", () => {
    expect(resolveSparklineTitle({ isOtc: false })).toBe("暂无走势数据");
    expect(
      resolveSparklineTitle({
        isOtc: true,
        intradayPoints: null,
        trendPoints: null
      })
    ).toBe("场外基金无盘中估值分时，暂无净值数据");
  });

  it("边界：恰好 2 点画得出一根线，按有数据处理", () => {
    expect(
      resolveSparklineTitle({ isOtc: false, intradayPoints: 2, trendPoints: 0 })
    ).toBe("当日分时走势（盘中实时）");
  });
});
