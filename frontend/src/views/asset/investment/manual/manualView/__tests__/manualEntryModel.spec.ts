import { describe, expect, it } from "vitest";

import {
  dividendModeOf,
  getFundOpLabel,
  isDividendLikeOf,
  isFundLike,
  isSellLikeOf,
  isSplitOf,
  quickAddFeeConfig,
  submitOpTypeOf
} from "../manualEntryModel";
import type { FundOpType } from "../manualEntryModel";

/** 未涉及的那一组用中性值 subscribe，避免误命中（它会命中卖出判定） */
const NEUTRAL_FUND: FundOpType = "subscribe";

describe("isFundLike", () => {
  it("基金与银行（类现金）共享同一组操作", () => {
    expect(isFundLike("fund")).toBe(true);
    expect(isFundLike("bank")).toBe(true);
  });

  it("证券、房产与空值都不算基金组", () => {
    expect(isFundLike("stock")).toBe(false);
    expect(isFundLike("property")).toBe(false);
    expect(isFundLike(null)).toBe(false);
    expect(isFundLike(undefined)).toBe(false);
  });
});

describe("isSellLikeOf：卖出类（证券卖出 / 基金赎回）", () => {
  it("证券账户只有 sell 算卖出类", () => {
    expect(isSellLikeOf("stock", "sell", NEUTRAL_FUND)).toBe(true);
    expect(isSellLikeOf("stock", "dividend", NEUTRAL_FUND)).toBe(false);
  });

  it("基金 / 银行只有 redeem 算卖出类", () => {
    expect(isSellLikeOf("fund", "buy", "redeem")).toBe(true);
    expect(isSellLikeOf("bank", "buy", "redeem")).toBe(true);
    expect(isSellLikeOf("fund", "buy", "convert")).toBe(false);
  });

  it("基金组的判定不串到证券组：证券账户下 redeem 不算卖出", () => {
    expect(isSellLikeOf("stock", "buy", "redeem")).toBe(false);
  });

  it("未选账户时为 false（账户栏此时不该被过滤）", () => {
    expect(isSellLikeOf(null, "sell", "redeem")).toBe(false);
  });
});

describe("isDividendLikeOf / isSplitOf", () => {
  it("证券：dividend 是分红，split 是拆分", () => {
    expect(isDividendLikeOf("stock", "dividend", NEUTRAL_FUND)).toBe(true);
    expect(isSplitOf("stock", "split", NEUTRAL_FUND)).toBe(true);
    expect(isSplitOf("stock", "dividend", NEUTRAL_FUND)).toBe(false);
  });

  it("基金：dividend_reinvest 是分红，split 是拆分", () => {
    expect(isDividendLikeOf("fund", "buy", "dividend_reinvest")).toBe(true);
    expect(isSplitOf("fund", "buy", "split")).toBe(true);
    expect(isDividendLikeOf("fund", "buy", "split")).toBe(false);
  });

  it("基金赎回既不是分红也不是拆分", () => {
    expect(isDividendLikeOf("fund", "buy", "redeem")).toBe(false);
    expect(isSplitOf("fund", "buy", "redeem")).toBe(false);
  });
});

describe("dividendModeOf：DividendForm 子模式", () => {
  it("拆分优先于分红", () => {
    expect(dividendModeOf(true, "stock", "dividend")).toBe("split");
  });

  it("证券的 dividend 落到 dividend", () => {
    expect(dividendModeOf(false, "stock", "dividend")).toBe("dividend");
  });

  it("证券的非 dividend（如 buy）落到 dividend_reinvest", () => {
    expect(dividendModeOf(false, "stock", "buy")).toBe("dividend_reinvest");
  });

  it("基金侧不看 stockOpType，一律 dividend_reinvest", () => {
    expect(dividendModeOf(false, "fund", "buy")).toBe("dividend_reinvest");
  });
});

describe("submitOpTypeOf：确认记账走哪条通道", () => {
  it("分红与拆分都归 dividend", () => {
    expect(submitOpTypeOf(true, false, "buy", "subscribe")).toBe("dividend");
    expect(submitOpTypeOf(false, true, "buy", "subscribe")).toBe("dividend");
  });

  it("证券卖出、基金赎回归 sell", () => {
    expect(submitOpTypeOf(false, false, "sell", "subscribe")).toBe("sell");
    expect(submitOpTypeOf(false, false, "buy", "redeem")).toBe("sell");
  });

  it("买入 / 申购 / 定投 / 转换之外归 buy", () => {
    expect(submitOpTypeOf(false, false, "buy", "subscribe")).toBe("buy");
    expect(submitOpTypeOf(false, false, "buy", "drip")).toBe("buy");
  });

  it("转换不归 sell：它的提交发生在向导第 3 步，不走全局按钮", () => {
    expect(submitOpTypeOf(false, false, "buy", "convert")).toBe("buy");
  });
});

describe("getFundOpLabel：未实现分支占位文案", () => {
  it("枚举值翻成中文", () => {
    expect(getFundOpLabel("dividend_reinvest")).toBe("红利再投");
    expect(getFundOpLabel("split")).toBe("送股/拆分");
    expect(getFundOpLabel("convert")).toBe("转换");
    expect(getFundOpLabel("drip")).toBe("定投");
  });

  it("翻不出来就原样返回，不显示空白", () => {
    expect(getFundOpLabel("some_new_op")).toBe("some_new_op");
  });
});

describe("quickAddFeeConfig：极简建账的费率初值", () => {
  it("场外基金：申购费 1 折", () => {
    expect(quickAddFeeConfig("fund_platform")).toEqual({
      subscription_discount: 0.1
    });
  });

  it("证券：佣金万 2.5 且免五（min 为 null）", () => {
    expect(quickAddFeeConfig("securities")).toEqual({
      commission: { rate: 0.00025, min: null }
    });
  });

  it("其余渠道不写死费率，交回后端默认值", () => {
    expect(quickAddFeeConfig("other")).toBeUndefined();
    expect(quickAddFeeConfig("")).toBeUndefined();
  });
});
