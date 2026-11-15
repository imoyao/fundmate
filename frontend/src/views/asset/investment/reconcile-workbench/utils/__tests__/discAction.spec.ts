/**
 * 「这条差异该点哪个按钮」的回归网（#3125）。
 *
 * 两个方向都错过一次就会教坏用户：
 * - 给无锚点差异配「补录这笔」→ 用户被引导去编造一笔不存在的交易凑数；
 * - 给真数量差异配「以此为准」→ 错数据被固化成基准，从此再也对不出来。
 *
 * 所以这里不只测「no_anchor → anchor」，也测「其它类型一律不许走到 anchor」。
 */
import { describe, expect, it } from "vitest";

import {
  DISC_ACTION_LABELS,
  defaultSupplementKind,
  discActionOf
} from "../discAction";

describe("差异类型 → 动作", () => {
  it("no_anchor 走「以此为准」", () => {
    expect(discActionOf({ discrepancy_type: "no_anchor" })).toBe("anchor");
    expect(DISC_ACTION_LABELS.anchor).toBe("以此为准");
  });

  it.each(["quantity", "cost", "cash", "orphan", "some_future_type"])(
    "%s 仍走「补录这笔」（不确认现状）",
    type => {
      expect(discActionOf({ discrepancy_type: type })).toBe("supplement");
      expect(DISC_ACTION_LABELS.supplement).toBe("补录这笔");
    }
  );

  it("按钮文案与动作同源：不会出现「按钮说补录、实际写基准」", () => {
    const row = { discrepancy_type: "no_anchor" };
    expect(DISC_ACTION_LABELS[discActionOf(row)]).toBe("以此为准");
  });
});

describe("弹窗打开时的默认模式", () => {
  it("no_anchor 进来就是「以此为准」，不是补一笔", () => {
    expect(defaultSupplementKind({ discrepancy_type: "no_anchor" })).toBe(
      "anchor"
    );
  });

  it("其它类型、空值都退回补一笔", () => {
    expect(defaultSupplementKind({ discrepancy_type: "quantity" })).toBe(
      "increment"
    );
    expect(defaultSupplementKind(null)).toBe("increment");
    expect(defaultSupplementKind(undefined)).toBe("increment");
  });
});
