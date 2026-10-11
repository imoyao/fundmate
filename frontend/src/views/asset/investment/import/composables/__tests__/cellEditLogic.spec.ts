import { describe, expect, it } from "vitest";
import { isMissingAmount, recalcAfterEdit, smartFill } from "../cellEditLogic";

/** 最小行形态：只带被测字段与互算所需的邻居字段 */
function makeRow(partial: Record<string, unknown>) {
  return partial as any;
}

describe("smartFill（编辑字段自身 NaN 时从另两项互推）", () => {
  it("改数量但数量为空：由金额 ÷ 单价补齐并标记 smartFilled", () => {
    const row = makeRow({ quantity: "", price: 10, amount: 100 });
    smartFill(row, "quantity");
    expect(row.quantity).toBe(10);
    expect(row.smartFilled).toBe(true);
  });

  it("改单价但单价为空：由金额 ÷ 数量补齐", () => {
    const row = makeRow({ quantity: 4, price: "", amount: 100 });
    smartFill(row, "price");
    expect(row.price).toBe(25);
    expect(row.smartFilled).toBe(true);
  });

  it("两项齐全时不改动任何值、不标记", () => {
    const row = makeRow({ quantity: 4, price: 25, amount: 100 });
    smartFill(row, "quantity");
    expect(row).toEqual({ quantity: 4, price: 25, amount: 100 });
  });

  it("金额也缺失时无法互推，保持原状", () => {
    const row = makeRow({ quantity: "", price: "", amount: "" });
    smartFill(row, "quantity");
    expect(row.quantity).toBe("");
  });
});

describe("recalcAfterEdit（§6.2 金额自动计算）", () => {
  it("改数量 → 金额 = 数量 × 单价（2 位）", () => {
    const row = makeRow({ quantity: 150, price: 10, amount: 1000 });
    recalcAfterEdit(row, "quantity");
    expect(row.amount).toBe(1500);
  });

  it("改单价 → 金额同步（含浮点尾巴收敛到 2 位）", () => {
    const row = makeRow({ quantity: 3, price: 0.1, amount: 999 });
    recalcAfterEdit(row, "price");
    expect(row.amount).toBe(0.3);
  });

  it("数量或单价无效时不重算（交给 smartFill / 行高亮）", () => {
    const row = makeRow({ quantity: "", price: 10, amount: 100 });
    recalcAfterEdit(row, "quantity");
    expect(row.amount).toBe(100);
  });

  it("改金额 → 有数量则反算单价（4 位）", () => {
    const row = makeRow({ quantity: 200, price: 5, amount: 500 });
    recalcAfterEdit(row, "amount");
    expect(row.price).toBe(2.5);
  });

  it("改金额 → 数量缺失但单价在：反推数量", () => {
    const row = makeRow({ quantity: "", price: 10, amount: 100 });
    recalcAfterEdit(row, "amount");
    expect(row.quantity).toBe(10);
  });

  it("改金额 → 两者均缺失则不计算（§6.2 明文）", () => {
    const row = makeRow({ quantity: "", price: "", amount: 100 });
    recalcAfterEdit(row, "amount");
    expect(row.quantity).toBe("");
    expect(row.price).toBe("");
    expect(row.amount).toBe(100);
  });

  it("金额非数值：不动任何字段", () => {
    const row = makeRow({ quantity: 10, price: 10, amount: "abc" });
    recalcAfterEdit(row, "amount");
    expect(row.price).toBe(10);
  });

  it("非编辑字段：不动任何字段", () => {
    const row = makeRow({ quantity: 10, price: 10, amount: 999 });
    recalcAfterEdit(row, "symbol");
    expect(row.amount).toBe(999);
  });
});

describe("isMissingAmount（金额列 cell-missing 判定）", () => {
  it.each([null, undefined, "", "abc", NaN])("缺失值 %p → true", v => {
    expect(isMissingAmount(makeRow({ amount: v }))).toBe(true);
  });

  it("0 是有效金额 → false", () => {
    expect(isMissingAmount(makeRow({ amount: 0 }))).toBe(false);
  });

  it("正常数值 → false", () => {
    expect(isMissingAmount(makeRow({ amount: 123.45 }))).toBe(false);
  });
});
