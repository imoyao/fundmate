import { describe, expect, it } from "vitest";
import { getLedgerColor, resolveLedgerBadge } from "../ledger";

/**
 * 账户徽标的取值优先级（2026-10-28 事故回归）。
 *
 * 事故：账户列表「银行」分组里，微众银行(ledger_type=bank) 显示「银」，而它的幽灵账户
 * 「深圳前海微众银行」(ledger_type=fund) 显示「基」——同一机构两个账户、两个标签。
 * 用户把后者的渠道类别改成「银行」后，徽标仍是「基」：因为旧代码读的是 ledger_type，
 * 而 ledger_type 编辑时不可变（409），用户永远改不掉。
 *
 * 后端模型注释与设计文档 §2.3 明确：类型标签一律只读 channel_category。这里钉住优先级。
 */
describe("resolveLedgerBadge", () => {
  it("渠道类别优先于 ledger_type —— 银行渠道的 fund 账户也显示「银」", () => {
    // 就是事故现场：ledger_type 说基金，channel_category 说银行
    expect(
      resolveLedgerBadge({ channelCategory: "bank", type: "fund" }).label
    ).toBe("银");
  });

  it("渠道类别齐全时按渠道给字", () => {
    expect(resolveLedgerBadge({ channelCategory: "securities" }).label).toBe(
      "证"
    );
    expect(resolveLedgerBadge({ channelCategory: "fund_platform" }).label).toBe(
      "基"
    );
    expect(resolveLedgerBadge({ channelCategory: "insurance" }).label).toBe(
      "保"
    );
    expect(resolveLedgerBadge({ channelCategory: "futures" }).label).toBe("期");
    expect(resolveLedgerBadge({ channelCategory: "other" }).label).toBe("其");
  });

  it("没有渠道类别时回退到 ledger_type（兼容旧调用方）", () => {
    expect(resolveLedgerBadge({ type: "bank" }).label).toBe("银");
    expect(resolveLedgerBadge({ type: "stock" }).label).toBe("股");
    expect(resolveLedgerBadge({ type: "fund" }).label).toBe("基");
    expect(resolveLedgerBadge({ type: "property" }).label).toBe("物");
  });

  it("显式 label 最高优先（自定义文案不受字段影响）", () => {
    expect(
      resolveLedgerBadge({ label: "已删", channelCategory: "bank" }).label
    ).toBe("已删");
  });

  it("未知值原样返回，不吞成空白", () => {
    expect(resolveLedgerBadge({ channelCategory: "某个新渠道" }).label).toBe(
      "某个新渠道"
    );
    expect(resolveLedgerBadge({ type: "deleted" }).label).toBe("已删");
    expect(resolveLedgerBadge({}).label).toBe("");
  });

  it("颜色跟着渠道类别走，银行与基金平台不同色", () => {
    const bank = resolveLedgerBadge({ channelCategory: "bank", type: "fund" });
    const fund = resolveLedgerBadge({ channelCategory: "fund_platform" });
    expect(bank.color).not.toBe(fund.color);
    expect(bank.color).toBe(getLedgerColor("bank"));
  });
});

describe("getLedgerColor", () => {
  it("两套值域都有色，不会掉到中性灰", () => {
    const neutral = "var(--color-neutral)";
    for (const key of ["bank", "stock", "fund", "property"]) {
      expect(getLedgerColor(key)).not.toBe(neutral);
    }
    for (const key of ["securities", "fund_platform", "insurance", "futures"]) {
      expect(getLedgerColor(key)).not.toBe(neutral);
    }
  });

  it("未知键回退中性色", () => {
    expect(getLedgerColor("nope")).toBe("var(--color-neutral)");
  });
});
