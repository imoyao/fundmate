/**
 * 「份额与流水不自洽」面板一键清仓载荷的回归网。
 *
 * 这个动作不可逆（写持仓 quantity=0 + 锚点归零），且恰好是本面板命中那批
 * （流水净额 ≤ 0）——recompute 被后端硬拦、increment 差额恒定，只有 set 0 合法。
 * 一旦有人把 kind/quantity 改错，用户点了要么 400、要么越补越乱，且没有报错提示。
 */
import { describe, expect, it } from "vitest";

import type { ShareIntegrityItem } from "@/api/reconciliation";
import {
  buildClearSharePayload,
  clearShareConfirmText,
  clearShareResultText
} from "../clearSharePayload";

function item(overrides: Partial<ShareIntegrityItem> = {}): ShareIntegrityItem {
  return {
    position_id: 548,
    symbol: "SZ127094",
    name: "红墙转债",
    ledger_id: 12,
    quantity_now: 50,
    quantity_if_recomputed: 0,
    diff: -50,
    flow_net: 0,
    flow_state: "netted_out",
    adjustment_txns: [],
    remedy: { action: "review_adjustment", hint: "" },
    ...overrides
  };
}

describe("buildClearSharePayload", () => {
  it("走 set + quantity=0：唯一合法的清仓写路径", () => {
    const p = buildClearSharePayload(item());
    expect(p.kind).toBe("set");
    expect(p.quantity).toBe(0);
  });

  it("绝不退化成 recompute（净额 ≤ 0 会被后端硬拦）或 increment（差额恒定）", () => {
    const p = buildClearSharePayload(item());
    expect(p.kind).not.toBe("recompute");
    expect(p.kind).not.toBe("increment");
  });

  it("带 symbol（后端 set 必填）与 ledger_id（区分同名标的所在账户）", () => {
    const p = buildClearSharePayload(item());
    expect(p.symbol).toBe("SZ127094");
    expect(p.ledger_id).toBe(12);
  });

  it("不传 discrepancy_id：set 0 走 _clear_position_by_bill，靠位置定位而非差异行", () => {
    expect(buildClearSharePayload(item()).discrepancy_id).toBeUndefined();
  });

  it("reason 写明账上与流水净额，审计可追溯成因", () => {
    expect(buildClearSharePayload(item()).reason).toContain("50");
    expect(buildClearSharePayload(item()).reason).toContain("流水净额 0");
  });
});

describe("clearShareConfirmText", () => {
  it("oversold 明确提醒多半是漏记买入，先补别清", () => {
    expect(clearShareConfirmText(item({ flow_state: "oversold" }))).toContain(
      "漏记了买入"
    );
  });

  it("netted_out 说明可能是真清仓、也可能流水没记全", () => {
    expect(clearShareConfirmText(item({ flow_state: "netted_out" }))).toContain(
      "流水没记全"
    );
  });

  it("两种形态都要求账单确认，并说明可撤销", () => {
    for (const flow_state of ["oversold", "netted_out"] as const) {
      const text = clearShareConfirmText(item({ flow_state }));
      expect(text).toContain("券商账单确认");
      expect(text).toContain("撤销");
    }
  });
});

describe("clearShareResultText", () => {
  it("明确告诉用户提示已更新（不是含糊的「成功」）", () => {
    expect(clearShareResultText()).toContain("份额自洽提示已更新");
  });
});
