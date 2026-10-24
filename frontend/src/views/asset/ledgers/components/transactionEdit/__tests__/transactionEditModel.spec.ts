/**
 * 编辑交易弹窗的纯口径（#980 拆分时抽出）。
 *
 * 重点盯：反算的「不写回」语义（返回 null 而不是 0）、金额的正反算精度、
 * 资产类型的四级兜底、以及关闭后空表单与打开快照的结构一致性
 * （两者结构不同会让 `useFormDirty` 的 JSON 基线对不上）。
 */
import { describe, expect, it } from "vitest";
import {
  blankForm,
  buildUpdatePayload,
  formSnapshotOf,
  isFundAssetType,
  isStockAssetType,
  quantityMeta,
  recalcAmount,
  recalcShares,
  resolveAssetType
} from "../transactionEditModel";

describe("resolveAssetType", () => {
  it("外部传入优先于记录里的任何字段", () => {
    expect(resolveAssetType({ asset_type: "fund", type: "buy" }, "stock")).toBe(
      "stock"
    );
  });

  it("按 asset_type → type → security_type → position_type 逐级兜底", () => {
    expect(resolveAssetType({ asset_type: "fund", type: "buy" })).toBe("fund");
    expect(resolveAssetType({ type: "stock" })).toBe("stock");
    expect(resolveAssetType({ security_type: "bond" })).toBe("bond");
    expect(resolveAssetType({ position_type: "crypto" })).toBe("crypto");
  });

  it("空对象 / null 都给出空串（不是 undefined，模板里要能直接比较）", () => {
    expect(resolveAssetType(null)).toBe("");
    expect(resolveAssetType({})).toBe("");
    expect(resolveAssetType({ asset_type: "" }, "")).toBe("");
  });
});

describe("isFundAssetType / isStockAssetType", () => {
  it("基金类含货币基金", () => {
    expect(isFundAssetType("fund")).toBe(true);
    expect(isFundAssetType("money_fund")).toBe(true);
    expect(isFundAssetType("stock")).toBe(false);
  });

  it("证券类四种", () => {
    for (const t of ["stock", "etf", "bond", "convertible"]) {
      expect(isStockAssetType(t)).toBe(true);
    }
    expect(isStockAssetType("fund")).toBe(false);
    expect(isStockAssetType("crypto")).toBe(false);
  });
});

describe("quantityMeta", () => {
  it("基金 4 位小数、步进 0.0001；其余整数股", () => {
    expect(quantityMeta("fund")).toEqual({ precision: 4, step: 0.0001 });
    expect(quantityMeta("money_fund")).toEqual({
      precision: 4,
      step: 0.0001
    });
    expect(quantityMeta("stock")).toEqual({ precision: 0, step: 1 });
    expect(quantityMeta("")).toEqual({ precision: 0, step: 1 });
  });
});

describe("recalcShares（金额 → 份额）", () => {
  it("(amount - fee) / nav，保留 4 位小数", () => {
    expect(recalcShares(1000, 2, 0)).toBe(500);
    expect(recalcShares(1000, 2, 10)).toBe(495);
    expect(recalcShares(1000, 3.3333, 0)).toBe(300.003);
  });

  it("净值为 0 或负数时返回 null（不能除零，也不能给出负份额）", () => {
    expect(recalcShares(1000, 0, 0)).toBeNull();
    expect(recalcShares(1000, -1, 0)).toBeNull();
  });

  it("金额或净值为空时返回 null —— 表示「不写回」，而不是把份额清成 0", () => {
    expect(recalcShares(null, 2, 0)).toBeNull();
    expect(recalcShares(1000, null, 0)).toBeNull();
    expect(recalcShares(undefined, undefined, undefined)).toBeNull();
  });

  it("金额为负不反算（手输错值时不要把份额带偏）", () => {
    expect(recalcShares(-1, 2, 0)).toBeNull();
  });

  it("金额为 0 是合法输入，反算出 0 份额", () => {
    expect(recalcShares(0, 2, 0)).toBe(0);
  });

  it("fee 缺省按 0 计", () => {
    expect(recalcShares(1000, 2, undefined)).toBe(500);
    expect(recalcShares(1000, 2, null)).toBe(500);
  });
});

describe("recalcAmount（数量 → 金额）", () => {
  it("qty * price + fee，保留 2 位小数", () => {
    expect(recalcAmount(100, 1.23, 5)).toBe(128);
    expect(recalcAmount(100, 2, 0)).toBe(200);
  });

  it("浮点误差被抹平（0.1 × 3 不出现 0.30000000000000004）", () => {
    expect(recalcAmount(3, 0.1, 0)).toBe(0.3);
  });

  it("数量或单价为空时返回 null（不写回）", () => {
    expect(recalcAmount(null, 2, 0)).toBeNull();
    expect(recalcAmount(100, null, 0)).toBeNull();
  });

  it("负数不计算", () => {
    expect(recalcAmount(-1, 2, 0)).toBeNull();
    expect(recalcAmount(100, -2, 0)).toBeNull();
  });

  it("数量为 0 时金额 = 手续费", () => {
    expect(recalcAmount(0, 2, 5)).toBe(5);
  });
});

describe("formSnapshotOf / blankForm", () => {
  it("快照逐字段对齐记录，空日期转 null、notes 转空串", () => {
    expect(
      formSnapshotOf({
        quantity: 100,
        price: 2,
        amount: 200,
        fee: 0,
        trade_date: "2026-03-10",
        confirm_date: "",
        notes: undefined
      })
    ).toEqual({
      quantity: 100,
      price: 2,
      amount: 200,
      fee: 0,
      trade_date: "2026-03-10",
      confirm_date: null,
      notes: ""
    });
  });

  it("记录缺字段时补 null（不留下 undefined，否则脏基线的 JSON 少 key）", () => {
    const snap = formSnapshotOf({});
    expect(Object.keys(snap).sort()).toEqual(Object.keys(blankForm()).sort());
    expect(snap).toEqual(blankForm());
  });

  it("传入 null 也给全字段快照", () => {
    expect(formSnapshotOf(null)).toEqual(blankForm());
  });

  it("每次返回新对象，改一个不影响另一个", () => {
    const a = blankForm();
    const b = blankForm();
    a.notes = "改过";
    expect(b.notes).toBe("");
  });
});

describe("buildUpdatePayload", () => {
  it("只提交 7 个可编辑字段", () => {
    const payload = buildUpdatePayload({
      quantity: 100,
      price: 2,
      amount: 200,
      fee: 1,
      trade_date: "2026-03-10",
      confirm_date: "2026-03-11",
      notes: "备注"
    });
    expect(payload).toEqual({
      quantity: 100,
      price: 2,
      amount: 200,
      fee: 1,
      trade_date: "2026-03-10",
      confirm_date: "2026-03-11",
      notes: "备注"
    });
    // 交易 id / ledger_id 走 URL，不进 body
    expect(payload).not.toHaveProperty("id");
    expect(payload).not.toHaveProperty("ledger_id");
  });

  it("空日期转 null（后端按 null 表示「未确认」）", () => {
    const payload = buildUpdatePayload({
      ...blankForm(),
      trade_date: "",
      confirm_date: ""
    });
    expect(payload.trade_date).toBeNull();
    expect(payload.confirm_date).toBeNull();
  });
});
