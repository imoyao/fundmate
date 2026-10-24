/**
 * 账户卡片的展示口径（#980 拆分时抽出）。
 *
 * 重点盯三处「方向容易写反」的判断：归档是取反表达、第几位是 1 起而下标是 0 起、
 * 银行的活期余额为空时要退回持仓盈亏而不是显示 ¥0.00。
 */
import { describe, expect, it } from "vitest";
import {
  archiveAriaLabel,
  archiveToggleLabel,
  deleteAriaLabel,
  dragAriaLabel,
  dragTitle,
  hasLinkedLiability,
  hasRowActions,
  isArchived,
  pnlLabelOf,
  pnlMetricKindOf,
  reorderTargetOf,
  showStaleBadge
} from "../ledgerCardModel";

describe("isArchived", () => {
  it("只有显式的 is_active === false 才算归档", () => {
    expect(isArchived({ is_active: false })).toBe(true);
    expect(isArchived({ is_active: true })).toBe(false);
    // undefined 不能当归档——新建的账户还没取到 is_active
    expect(isArchived({})).toBe(false);
    expect(isArchived(null)).toBe(false);
  });
});

describe("hasRowActions", () => {
  it("只认数字 id（草稿卡的 id 可能是字符串占位）", () => {
    expect(hasRowActions({ id: 12 })).toBe(true);
    expect(hasRowActions({ id: 0 })).toBe(true);
    expect(hasRowActions({ id: "12" })).toBe(false);
    expect(hasRowActions({})).toBe(false);
  });
});

describe("showStaleBadge", () => {
  it("缺省按 0 处理，不渲染角标", () => {
    expect(showStaleBadge(undefined)).toBe(false);
    expect(showStaleBadge(0)).toBe(false);
    expect(showStaleBadge(1)).toBe(true);
    expect(showStaleBadge(7)).toBe(true);
  });
});

describe("hasLinkedLiability", () => {
  it("只有银行账户且负债大于 0 才显示", () => {
    expect(
      hasLinkedLiability({ ledger_type: "bank", linked_liability: 1 })
    ).toBe(true);
    expect(
      hasLinkedLiability({ ledger_type: "bank", linked_liability: 0 })
    ).toBe(false);
    expect(
      hasLinkedLiability({ ledger_type: "bank", linked_liability: null })
    ).toBe(false);
    expect(
      hasLinkedLiability({ ledger_type: "stock", linked_liability: 100 })
    ).toBe(false);
  });
});

describe("pnlLabelOf", () => {
  it("三类账户各自的中文标题", () => {
    expect(pnlLabelOf("bank")).toBe("活期余额");
    expect(pnlLabelOf("property")).toBe("估值");
    expect(pnlLabelOf("stock")).toBe("持仓盈亏");
    expect(pnlLabelOf("fund")).toBe("持仓盈亏");
    expect(pnlLabelOf(undefined)).toBe("持仓盈亏");
  });
});

describe("pnlMetricKindOf", () => {
  it("银行且有活期余额 → cash", () => {
    expect(pnlMetricKindOf({ ledger_type: "bank", cash_balance: 0 })).toBe(
      "cash"
    );
    expect(pnlMetricKindOf({ ledger_type: "bank", cash_balance: 1234.5 })).toBe(
      "cash"
    );
  });

  it("银行的活期余额为空 → 退回 pnl（不能显示成 ¥0.00）", () => {
    expect(pnlMetricKindOf({ ledger_type: "bank", cash_balance: null })).toBe(
      "pnl"
    );
    expect(pnlMetricKindOf({ ledger_type: "bank" })).toBe("pnl");
  });

  it("实物 → count", () => {
    expect(pnlMetricKindOf({ ledger_type: "property" })).toBe("count");
    // 实物即使带了 cash_balance 也按项数显示
    expect(
      pnlMetricKindOf({ ledger_type: "property", cash_balance: 100 })
    ).toBe("count");
  });

  it("其余 → pnl", () => {
    expect(pnlMetricKindOf({ ledger_type: "stock" })).toBe("pnl");
    expect(pnlMetricKindOf({})).toBe("pnl");
  });
});

describe("archiveToggleLabel / archiveAriaLabel", () => {
  it("文案与 aria-label 同向翻转", () => {
    expect(archiveToggleLabel(false)).toBe("归档");
    expect(archiveToggleLabel(true)).toBe("激活");
    expect(archiveAriaLabel("招行卡", false)).toBe("归档账户 招行卡");
    expect(archiveAriaLabel("招行卡", true)).toBe("激活账户 招行卡");
  });
});

describe("deleteAriaLabel", () => {
  it("带上账户名，避免读屏时两次「删除」无法区分", () => {
    expect(deleteAriaLabel("招行卡")).toBe("删除账户 招行卡");
  });
});

describe("dragAriaLabel / dragTitle", () => {
  it("念出「第几位 / 共几位」（0 起下标转 1 起）", () => {
    expect(dragAriaLabel("招行卡", 0, 5)).toBe(
      "调整顺序：招行卡，当前第 1 / 5 位，用上下方向键移动"
    );
    expect(dragAriaLabel("招行卡", 2, 5)).toBe(
      "调整顺序：招行卡，当前第 3 / 5 位，用上下方向键移动"
    );
  });

  it("位置信息缺省时按「1 / 1」兜底，不出现 NaN", () => {
    expect(dragAriaLabel("招行卡")).toBe(
      "调整顺序：招行卡，当前第 1 / 1 位，用上下方向键移动"
    );
  });

  it("title 提示拖拽与键盘两种方式", () => {
    expect(dragTitle("招行卡")).toBe("拖拽或用方向键调整顺序：招行卡");
  });
});

describe("reorderTargetOf", () => {
  it("↑ / ↓ 在当前下标上移一位", () => {
    expect(reorderTargetOf("up", 2, 5)).toBe(1);
    expect(reorderTargetOf("down", 2, 5)).toBe(3);
  });

  it("Home / End 到首尾", () => {
    expect(reorderTargetOf("home", 3, 5)).toBe(0);
    expect(reorderTargetOf("end", 1, 5)).toBe(4);
  });

  it("越界不在本层夹紧（跨组语义交给页面层的 reorderLedgers）", () => {
    expect(reorderTargetOf("up", 0, 5)).toBe(-1);
    expect(reorderTargetOf("down", 4, 5)).toBe(5);
  });

  it("位置缺省按 0 / 1 兜底，End 落在 0", () => {
    expect(reorderTargetOf("up")).toBe(-1);
    expect(reorderTargetOf("down")).toBe(1);
    expect(reorderTargetOf("home")).toBe(0);
    expect(reorderTargetOf("end")).toBe(0);
  });
});
