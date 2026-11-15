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
    // 「怀疑份额本身错」时的另一条路，否则 manual 锚点会把真错固化。
    expect(supplementLabels("anchor").explain).toContain("按流水重算份额");
    expect(supplementLabels("increment").action).toBe("补录这笔");
  });
});
