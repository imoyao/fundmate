/**
 * 组合卡「目标达成」口径的回归网（2026-10-30 卡片重设计）。
 *
 * 钉住两条容易做反的口径：
 * 1. **数字不封顶**（144% 就是 144%，压成 100% 抹掉「超额」）；
 * 2. **进度条封顶 100%**（条只管满没满，不与数字抢着说「超了多少」）。
 * 另加三条边界：浮点取整、null ≠ 0、异常负值不撑出条外。
 */
import { describe, it, expect } from "vitest";
import { formatTargetProgress, targetFillWidth } from "../portfolioCardModel";

describe("目标达成：数字不封顶", () => {
  it("超额达成如实显示，不压成 100%", () => {
    expect(formatTargetProgress(144)).toBe("144%");
    expect(formatTargetProgress(240.5)).toBe("241%");
  });

  it("浮点按整数百分比展示（后端是原始乘积，不是已取整值）", () => {
    expect(formatTargetProgress(88.63)).toBe("89%");
    expect(formatTargetProgress(14.4)).toBe("14%");
  });

  it("0 与 null 不是同一种东西：0 显示 0%，null 返回空串由调用方不渲染", () => {
    expect(formatTargetProgress(0)).toBe("0%");
    expect(formatTargetProgress(null)).toBe("");
    expect(formatTargetProgress(undefined)).toBe("");
  });

  it("非有限值（NaN / Infinity）不显示成 NaN%", () => {
    expect(formatTargetProgress(Number.NaN)).toBe("");
    expect(formatTargetProgress(Number.POSITIVE_INFINITY)).toBe("");
  });
});

describe("目标达成：进度条封顶 100%", () => {
  it("超额时条封顶，数字另有交代", () => {
    expect(targetFillWidth(144)).toBe("100%");
    expect(targetFillWidth(88.63)).toBe("88.63%");
    expect(targetFillWidth(0.4)).toBe("0.4%");
  });

  it("无值 / 负值按 0，不反向填充", () => {
    expect(targetFillWidth(null)).toBe("0%");
    expect(targetFillWidth(undefined)).toBe("0%");
    expect(targetFillWidth(-12)).toBe("0%");
    expect(targetFillWidth(0)).toBe("0%");
  });
});
