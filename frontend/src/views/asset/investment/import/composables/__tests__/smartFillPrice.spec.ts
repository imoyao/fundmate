import { describe, expect, it } from "vitest";
import {
  PRICE_NOT_DERIVABLE_OPS,
  fillSmartPrice,
  shouldSmartFillPrice
} from "../smartFillPrice";
import { QTY_PRICE_OPTIONAL_OPS, isRowBlocked } from "../previewPredicates";

/**
 * 「金额 ÷ 份额 补单价」的口径回归网（#2903）。
 *
 * 背景：同一规则原先在 `useImportWizard.ts` 写了两份——OCR 通道无守卫、文件通道 4 条件，
 * 计算式逐字相同。卡面要求先判定「哪个口径是对的」，结论见 `smartFillPrice.ts` 头注释：
 * 两个都不对，文件通道那 4 个条件**把条件写反了**。
 *
 * 本文件钉住四件事：
 * 1. 该补的补：普通成交行（buy/sell/红利再投）缺价 → 金额 ÷ 份额，精度 4 位；
 * 2. 不该补的不补：不解析错误 / 疑似重复 / 资金划转 / 被消费 / 金额与份额无关的类型；
 * 3. 「旧守卫是空集」有机器证据——不对着卡面描述空谈；
 * 4. 补价后该行从「被拦」变「可入账」（这是补价的产品意义，不是副作用）。
 */

/** 一条普通买入行：有份额、有金额、缺单价。 */
function row(patch: Record<string, unknown> = {}): any {
  return {
    op_type: "buy",
    quantity: "100",
    price: "",
    amount: "1234",
    ...patch
  };
}

describe("fillSmartPrice 该补的行", () => {
  it("普通买入：金额 1234 / 份额 100 → 单价 12.34，并标记 smartFilled", () => {
    const r = row();
    expect(fillSmartPrice(r)).toBe(true);
    expect(r.price).toBe(12.34);
    expect(r.smartFilled).toBe(true);
  });

  it("price 为 0 与 price 为非法串都算「缺价」", () => {
    expect(fillSmartPrice(row({ price: 0 }))).toBe(true);
    expect(fillSmartPrice(row({ price: "abc" }))).toBe(true);
    expect(fillSmartPrice(row({ price: "0.0000" }))).toBe(true);
  });

  it("卖出与红利再投同样补（红利再投的金额÷份额就是再投净值）", () => {
    const sell = row({ op_type: "sell" });
    expect(fillSmartPrice(sell)).toBe(true);
    expect(sell.price).toBe(12.34);

    const reinvest = row({
      op_type: "dividend_reinvest",
      quantity: "50",
      amount: "75"
    });
    expect(fillSmartPrice(reinvest)).toBe(true);
    expect(reinvest.price).toBe(1.5);
  });

  it("精度 4 位（与 cellEditLogic.smartFill 同款），不留浮点尾巴", () => {
    const r = row({ quantity: "3", amount: "1000" });
    fillSmartPrice(r);
    expect(r.price).toBe(333.3333);
  });

  it("只改 price / smartFilled，不动 amount 与 quantity", () => {
    const r = row();
    fillSmartPrice(r);
    expect(r.amount).toBe("1234");
    expect(r.quantity).toBe("100");
  });

  it("补价后该行不再被 isRowBlocked 拦截（补价的产品意义：从「需修正」变可入账）", () => {
    const r = row();
    expect(isRowBlocked(r)).toBe(true);
    fillSmartPrice(r);
    expect(isRowBlocked(r)).toBe(false);
  });
});

describe("fillSmartPrice 不该补的行", () => {
  it("已有正单价：保持原值，不覆盖", () => {
    const r = row({ price: "12.5" });
    expect(fillSmartPrice(r)).toBe(false);
    expect(r.price).toBe("12.5");
    expect(r.smartFilled).toBeUndefined();
  });

  it("解析错误 / 疑似重复 / 资金划转 / 被配对消费：数据不可信或不入账", () => {
    for (const patch of [
      { error: "nope" },
      { is_duplicate: true },
      { is_cash_transfer: true },
      { consumed_by: 7 }
    ]) {
      const r = row(patch);
      expect(fillSmartPrice(r), JSON.stringify(patch)).toBe(false);
      expect(r.price).toBe("");
    }
  });

  it("数值前提不足：份额为 0 / 份额缺失 / 金额缺失 / 金额非法 / 金额非正", () => {
    for (const patch of [
      { quantity: 0 },
      { quantity: "" },
      { amount: "" },
      { amount: "abc" },
      // 负金额（部分数据源把卖出记成负数）会算出负单价——补了比不补更糟
      { amount: -1234 },
      { amount: 0 }
    ]) {
      const r = row(patch);
      expect(fillSmartPrice(r), JSON.stringify(patch)).toBe(false);
    }
  });

  it("金额与「份额对应的成交额」无关的类型：反推出来的不是单价", () => {
    for (const op of [
      "tax",
      "dividend",
      "dividend_cash",
      "split",
      "bond_redeem"
    ]) {
      const r = row({ op_type: op });
      expect(fillSmartPrice(r), op).toBe(false);
      expect(r.price, op).toBe("");
    }
  });

  it("货币基金（净值恒 1）与逆回购（金额与张数不成单价×数量）：不补", () => {
    for (const type of ["money_fund", "reverse_repo"]) {
      const r = row({ type });
      expect(fillSmartPrice(r), type).toBe(false);
    }
  });
});

describe("#2903 的定案依据（机器证据，不是卡面叙述）", () => {
  /** 旧文件通道的 4 条件守卫，逐字照抄修复前的写法。 */
  const legacyFileGuard = (r: any): boolean =>
    !isRowBlocked(r) && !r.is_cash_transfer && !r.error && !r.is_duplicate;

  it("旧守卫对普通缺价行恒 false：`!isRowBlocked` 与「缺价」互斥 ⇒ 该分支对它要服务的行从未执行", () => {
    for (const price of ["", 0, "0.0000", "abc"]) {
      const r = row({ price });
      expect(isRowBlocked(r), `price=${price}`).toBe(true);
      expect(legacyFileGuard(r), `price=${price}`).toBe(false);
    }
  });

  it("旧守卫只放行 isRowBlocked 的豁免类型——包括不该补价的税额/兑付/分红", () => {
    for (const op of ["tax", "dividend", "bond_redeem", "split"]) {
      const r = row({ op_type: op });
      expect(legacyFileGuard(r), op).toBe(true);
      expect(shouldSmartFillPrice(r), op).toBe(false);
    }
  });

  it("排除集 = QTY_PRICE_OPTIONAL_OPS 去掉 dividend_reinvest（差集是有意的，改一个必须看另一个）", () => {
    const diff = [...QTY_PRICE_OPTIONAL_OPS].filter(
      op => !PRICE_NOT_DERIVABLE_OPS.has(op)
    );
    expect(diff).toEqual(["dividend_reinvest"]);
  });
});
