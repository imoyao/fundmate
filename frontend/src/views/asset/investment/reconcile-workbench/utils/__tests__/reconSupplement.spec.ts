import { describe, expect, it } from "vitest";
import type { DiscrepancyItem } from "@/api/reconciliation";
import { inferSupplementOpType } from "../reconSupplement";

/**
 * 方向判据的回归网。
 *
 * 最贵的一条是「orphan 不预填卖出」：它拿真实形态（`actual_value = 0`、
 * `diff` 为负）喂进去，若有人把 `discrepancy_type !== "quantity"` 那道闸删掉
 * （看起来像是「多余的判断」），本条立刻红——否则用户会被引导去补一笔
 * 根本不存在的卖出。
 */
function makeRow(patch: Partial<DiscrepancyItem>): DiscrepancyItem {
  return {
    id: 1,
    domain: "B",
    ledger_id: 12,
    symbol: "SZ000725",
    display_name: "京东方 A",
    discrepancy_type: "quantity",
    expected_value: null,
    actual_value: null,
    diff: null,
    status: "pending",
    is_permanent: false,
    first_detected_at: "2026-09-01T00:00:00Z",
    updated_at: null,
    ...patch
  };
}

describe("inferSupplementOpType", () => {
  it("没有差异行时不预填", () => {
    expect(inferSupplementOpType(null)).toBeNull();
  });

  it("流水比账上多 = 少记卖出 → sell", () => {
    const row = makeRow({
      expected_value: 2500,
      actual_value: 1500,
      diff: -1000
    });
    expect(inferSupplementOpType(row)).toBe("sell");
  });

  it("流水比账上少 = 少记买入 → buy", () => {
    const row = makeRow({
      expected_value: 1000,
      actual_value: 1500,
      diff: 500
    });
    expect(inferSupplementOpType(row)).toBe("buy");
  });

  it("两边一致（diff=0）不预填", () => {
    const row = makeRow({ expected_value: 1500, actual_value: 1500, diff: 0 });
    expect(inferSupplementOpType(row)).toBeNull();
  });

  it("diff 缺失时按 actual - expected 现算", () => {
    expect(
      inferSupplementOpType(
        makeRow({ expected_value: 3000, actual_value: 1000, diff: null })
      )
    ).toBe("sell");
    expect(
      inferSupplementOpType(
        makeRow({ expected_value: 1000, actual_value: 3000, diff: null })
      )
    ).toBe("buy");
  });

  it("两个数都缺时不预填（不替用户猜方向）", () => {
    expect(
      inferSupplementOpType(
        makeRow({ expected_value: null, actual_value: 1500, diff: null })
      )
    ).toBeNull();
    expect(
      inferSupplementOpType(
        makeRow({ expected_value: 1500, actual_value: null, diff: null })
      )
    ).toBeNull();
  });

  it("orphan 不预填卖出：持仓行没了不等于少记卖出", () => {
    const row = makeRow({
      discrepancy_type: "orphan",
      expected_value: 3700,
      actual_value: 0,
      diff: -3700
    });
    expect(inferSupplementOpType(row)).toBeNull();
  });

  it("cost 差异与买卖方向无关，不预填", () => {
    const row = makeRow({
      discrepancy_type: "cost",
      expected_value: 1.1,
      actual_value: 2.2,
      diff: 1.1
    });
    expect(inferSupplementOpType(row)).toBeNull();
  });
});
