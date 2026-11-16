/**
 * 裁决请求体的回归网（#3125）。
 *
 * 这里钉的都是「写错了也不会报错」的三类：
 * 1. `anchor` 带上 quantity/avg_price → 前端成了猜数字的来源；
 * 2. `increment` 漏 trade_date → 流水按确认日排序，列表像「日期错了」；
 * 3. 手续费不按 op_type 收口 → 给银证转账记一笔佣金。
 */
import { describe, expect, it } from "vitest";

import type { DiscrepancyItem } from "@/api/reconciliation";
import {
  adjustmentSuccessMessage,
  buildAdjustmentPayload,
  buildRecomputePayload,
  recomputeResultMessage,
  supplementLabels,
  type SupplementFormValue
} from "../adjustmentPayload";

function row(over: Partial<DiscrepancyItem> = {}): DiscrepancyItem {
  return {
    id: 42,
    domain: "B",
    ledger_id: 7,
    symbol: "SH600027",
    display_name: "华电国际",
    discrepancy_type: "no_anchor",
    expected_value: 0,
    actual_value: 600000,
    diff: 600000,
    status: "pending",
    is_permanent: false,
    first_detected_at: null,
    updated_at: null,
    ...over
  };
}

function form(over: Partial<SupplementFormValue> = {}): SupplementFormValue {
  return {
    kind: "anchor",
    op_type: "buy",
    quantity: undefined,
    avg_price: undefined,
    fee: undefined,
    confirm_date: "",
    snapshot_date: "",
    reason: "",
    ...over
  };
}

describe("anchor：只传差异 id", () => {
  it("不带 quantity / avg_price（份额成本由后端读持仓）", () => {
    // 模拟「用户先在『把持仓改成』里填了数、又切回以此为准」——残留值绝不能带上去。
    // 断言用 keys 而不是 toEqual：后者把 `quantity: undefined` 和不存在的键视为相等，
    // 变异成「明明写了 quantity」也照样绿（本用例第一版就是这样假通过）。
    const p = buildAdjustmentPayload(
      row(),
      form({ quantity: 123, avg_price: 9.9 }),
      "2026-11-15"
    );
    expect(Object.keys(p).sort()).toEqual(["discrepancy_id", "kind", "reason"]);
    expect(p.quantity).toBeUndefined();
    expect(p.avg_price).toBeUndefined();
    expect(p.symbol).toBeUndefined();
  });

  it("带备注时保留备注", () => {
    const p = buildAdjustmentPayload(
      row(),
      form({ reason: "券商快照为准" }),
      "2026-11-15"
    );
    expect(p.reason).toBe("券商快照为准");
  });
});

describe("increment：日期与手续费", () => {
  it("trade_date 与 confirm_date 同值（按真实成交日排序）", () => {
    const p = buildAdjustmentPayload(
      row({ discrepancy_type: "quantity" }),
      form({
        kind: "increment",
        op_type: "buy",
        quantity: 100,
        avg_price: 10,
        confirm_date: "2026-05-01"
      }),
      "2026-11-15"
    );
    expect(p.trade_date).toBe("2026-05-01");
    expect(p.confirm_date).toBe("2026-05-01");
    expect(p.op_type).toBe("buy");
  });

  it("存转（deposit/withdraw）不记手续费，哪怕表单里还留着旧值", () => {
    const p = buildAdjustmentPayload(
      row({ discrepancy_type: "quantity" }),
      form({ kind: "increment", op_type: "deposit", fee: 5 }),
      "2026-11-15"
    );
    expect(p.fee).toBeUndefined();
  });

  it("买卖保留手续费（含 0 元）", () => {
    const p = buildAdjustmentPayload(
      row({ discrepancy_type: "quantity" }),
      form({ kind: "increment", op_type: "sell", fee: 0 }),
      "2026-11-15"
    );
    expect(p.fee).toBe(0);
  });
});

describe("set：快照日缺省取今天", () => {
  it("没填生效日期就用业务日", () => {
    const p = buildAdjustmentPayload(
      row({ discrepancy_type: "quantity" }),
      form({ kind: "set", quantity: 60, avg_price: 10 }),
      "2026-11-15"
    );
    expect(p.snapshot_date).toBe("2026-11-15");
    expect(p.trade_date).toBeUndefined();
  });

  it("填了就按填的走", () => {
    const p = buildAdjustmentPayload(
      row({ discrepancy_type: "quantity" }),
      form({ kind: "set", snapshot_date: "2026-10-01" }),
      "2026-11-15"
    );
    expect(p.snapshot_date).toBe("2026-10-01");
  });
});

describe("结果文案", () => {
  it("没轧平必须说「还能继续补」，不能报已完成", () => {
    expect(adjustmentSuccessMessage("increment", true)).toContain("还没平");
    expect(adjustmentSuccessMessage("anchor", true)).toContain("还没消失");
  });

  it("轧平后按模式给文案", () => {
    expect(adjustmentSuccessMessage("anchor", false)).toBe("已以此为准");
    expect(adjustmentSuccessMessage("set", false)).toBe("持仓已改");
    expect(adjustmentSuccessMessage("increment", false)).toBe("这笔已补上");
  });

  it("标题/按钮/说明同源于同一处（不会各说各的）", () => {
    expect(supplementLabels("anchor").action).toBe("以此为准");
    expect(supplementLabels("anchor").submit).toBe("以此为准");
    expect(supplementLabels("anchor").explain).toContain("不用你填");
    // #3127：不能只说「缺基准、不用管」。账上份额未必可信，文案必须给出
    // 「怀疑份额本身错」时的另一条路（2026-11-16 起指向「核对流水 + 按账单改份额」，
    // 不再指向按流水重算），否则 manual 锚点会把真错固化。
    expect(supplementLabels("anchor").explain).toContain("核对流水");
    expect(supplementLabels("increment").action).toBe("补录这笔");
  });
});

describe("recompute：只传差异编号 + 标的（#3134）", () => {
  it("不带 quantity / avg_price，份额由后端按流水派生", () => {
    // 前端多传一个数字就是多一个把持仓写错的地方（与 anchor 同一约定）。
    const p = buildRecomputePayload(row({ discrepancy_type: "quantity" }));
    expect(Object.keys(p).sort()).toEqual([
      "discrepancy_id",
      "kind",
      "ledger_id",
      "symbol"
    ]);
    expect(p.kind).toBe("recompute");
    expect(p.discrepancy_id).toBe(42);
    expect(p.symbol).toBe("SH600027");
    expect(p.ledger_id).toBe(7);
  });
});

describe("recompute 结果文案", () => {
  const result = (over: {
    deleted?: boolean;
    quantity_after?: number;
    status?: string;
  }) => ({
    action: "recompute",
    before: {},
    after: {},
    log_id: 1,
    recompute: {
      log_id: 1,
      position_id: 944,
      symbol: "SZ159981",
      deleted: over.deleted ?? false,
      changed: true,
      quantity_before: 1000,
      quantity_after: over.quantity_after ?? 0,
      avg_price_before: 1,
      avg_price_after: 1,
      ownership_status_before: "active",
      ownership_status_after: over.deleted ? "deleted" : "cleared"
    },
    discrepancy: over.status
      ? {
          id: 378,
          status: over.status,
          diff: null,
          expected_value: null,
          actual_value: null
        }
      : undefined
  });

  it("差额平了：报出改后的份额并说已平", () => {
    const msg = recomputeResultMessage(result({ status: "cleared" }));
    expect(msg).toContain("已平");
    expect(msg).toContain("0 份");
  });

  it("差额还在：说清不是点错了，而是流水本身没记全", () => {
    const msg = recomputeResultMessage(result({ status: "pending" }));
    expect(msg).toContain("差额仍在");
    expect(msg).toContain("投资轨迹");
  });

  it("持仓被删：必须报出来（否则用户以为只是改了个数）", () => {
    const msg = recomputeResultMessage(result({ deleted: true }));
    expect(msg).toContain("已删除");
    expect(msg).toContain("1,000 份");
  });

  it("缺字段时退回一句中性的成功提示，不抛异常", () => {
    expect(
      recomputeResultMessage({
        action: "recompute",
        before: {},
        after: {},
        log_id: 1
      })
    ).toBe("已按流水重算份额");
  });
});
