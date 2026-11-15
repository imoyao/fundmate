/**
 * 「这条差异该点哪个按钮」的回归网（#3125 / #3134）。
 *
 * 三个方向都错过一次就会教坏用户：
 * - 给无锚点差异配「补录这笔」→ 用户被引导去编造一笔不存在的交易凑数；
 * - 给真数量差异配「以此为准」→ 错数据被固化成基准，从此再也对不出来；
 * - 给数量差异配「补录这笔」→ **点了没用**：补录同时写流水与持仓，差额两端同步移动
 *   （#3134 真库实测：补一笔卖出 3000，持仓 4000→1000、流水 3000→0，差额仍是 1000 份）。
 *
 * 所以这里不只测「no_anchor → anchor」，也测「其它类型一律不许走到 anchor」
 * 与「quantity 一律不许再走补录」。
 */
import { describe, expect, it } from "vitest";

import {
  DISC_ACTION_HINTS,
  DISC_ACTION_LABELS,
  defaultSupplementKind,
  discActionEvent,
  discActionOf
} from "../discAction";

describe("差异类型 → 动作", () => {
  it("no_anchor 走「以此为准」", () => {
    expect(discActionOf({ discrepancy_type: "no_anchor" })).toBe("anchor");
    expect(DISC_ACTION_LABELS.anchor).toBe("以此为准");
  });

  it("quantity 且理论份额 ≥ 0 走「按流水重算份额」", () => {
    expect(
      discActionOf({ discrepancy_type: "quantity", expected_value: 0 })
    ).toBe("recompute");
    expect(
      discActionOf({ discrepancy_type: "quantity", expected_value: 1600 })
    ).toBe("recompute");
    expect(DISC_ACTION_LABELS.recompute).toBe("按流水重算份额");
  });

  it("quantity 且理论份额为负（超卖）走「改成账单份额」", () => {
    // 照流水重算会把这只持仓清零，而 #3127 明确不敢批量清仓 ⇒ 交用户照账单填。
    expect(
      discActionOf({ discrepancy_type: "quantity", expected_value: -60064 })
    ).toBe("set");
    expect(DISC_ACTION_LABELS.set).toBe("改成账单份额");
  });

  it.each(["cost", "cash", "orphan", "some_future_type"])(
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

  it("每个动作都有文案与解释，不会渲染出空按钮", () => {
    for (const action of [
      "supplement",
      "anchor",
      "recompute",
      "set"
    ] as const) {
      expect(DISC_ACTION_LABELS[action].length).toBeGreaterThan(0);
      expect(DISC_ACTION_HINTS[action].length).toBeGreaterThan(0);
    }
  });
});

describe("动作 → 上抛事件", () => {
  it("只有 recompute 走独立事件（写路径不同：只改持仓、不建流水）", () => {
    expect(discActionEvent("recompute")).toBe("recompute");
  });

  it("其余动作都进补录弹窗（模式在弹窗里分流）", () => {
    expect(discActionEvent("supplement")).toBe("supplement");
    expect(discActionEvent("anchor")).toBe("supplement");
    expect(discActionEvent("set")).toBe("supplement");
  });
});

describe("弹窗打开时的默认模式", () => {
  it("no_anchor 进来就是「以此为准」，不是补一笔", () => {
    expect(defaultSupplementKind({ discrepancy_type: "no_anchor" })).toBe(
      "anchor"
    );
  });

  it("quantity 超卖进来就是「改成这个持仓」（set），不预填补一笔", () => {
    expect(
      defaultSupplementKind({
        discrepancy_type: "quantity",
        expected_value: -100000
      })
    ).toBe("set");
  });

  it("其它类型、空值都退回补一笔", () => {
    expect(defaultSupplementKind({ discrepancy_type: "cost" })).toBe(
      "increment"
    );
    expect(defaultSupplementKind(null)).toBe("increment");
    expect(defaultSupplementKind(undefined)).toBe("increment");
  });
});
