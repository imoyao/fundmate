/**
 * 晨星评级文案口径（#1440）。
 *
 * 钉两条最容易「写错了没人发现」的口径：
 * 1. 期限口径必须写在值里（晨星评级含风险调整维度，只显示数字会被读成「收益星级」）；
 * 2. 缺失 ≠ 0 星（货基 / 新基金常态无评级，显示 0 星是编造数据）。
 */
import { describe, it, expect } from "vitest";
import {
  formatRatingText,
  formatRatingDeltaText,
  RATING_PERIOD_LABEL
} from "../fundRatingFormat";

describe("formatRatingText：评级值文案", () => {
  it("值里带机构与期限口径（防「收益星级」误读）", () => {
    expect(formatRatingText(3)).toBe("3 星（3年期）");
    expect(formatRatingText(1)).toBe("1 星（3年期）");
    expect(formatRatingText(5)).toBe("5 星（3年期）");
    expect(RATING_PERIOD_LABEL).toBe("3年期");
  });

  it("无评级 → null（调用方显示「—」，绝不显示 0 星）", () => {
    expect(formatRatingText(null)).toBeNull();
    expect(formatRatingText(undefined)).toBeNull();
  });

  it("值越域 → null（「0 星」在晨星语境不存在，宁可显示「—」也不编造）", () => {
    expect(formatRatingText(0)).toBeNull();
    expect(formatRatingText(6)).toBeNull();
    expect(formatRatingText(3.5)).toBeNull();
  });
});

describe("formatRatingDeltaText：评级变化文案", () => {
  it("升 / 降都带方向与幅度", () => {
    expect(formatRatingDeltaText(1)).toBe("较上期 升1星");
    expect(formatRatingDeltaText(2)).toBe("较上期 升2星");
    expect(formatRatingDeltaText(-1)).toBe("较上期 降1星");
    expect(formatRatingDeltaText(-3)).toBe("较上期 降3星");
  });

  it("持平（0）与未知（null）→ null，不展示", () => {
    expect(formatRatingDeltaText(0)).toBeNull();
    expect(formatRatingDeltaText(null)).toBeNull();
    expect(formatRatingDeltaText(undefined)).toBeNull();
  });

  it("上期值不展示——当期值列不存历史，无从取上期星级", () => {
    // 文案里只有方向与幅度，没有「上期 4 星」这种说法
    expect(formatRatingDeltaText(-1)).not.toMatch(/上期\s*\d/);
  });
});
