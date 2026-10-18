import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";

/**
 * #2281：放开银证转账行导入勾选 + 三层感知的回归测试。
 *
 * 被测不变量（本期核心契约）：
 * 1. 转账行可勾选取决于现金账户关联状态：未关联禁用（isRowSelectable=false），
 *    已关联放开（isRowSelectable=true）——「能勾 = 能导」；
 * 2. 可勾但不默认勾：selectAllValid / 卡片批量勾选 / importNormalOnly
 *    均不纳入转账行，只有用户逐行显式勾选才进载荷；
 * 3. 批量取消（卡片复选框取消）走宽口径，手动勾上的转账行一并清除；
 * 4. 横幅双态：未关联引导态 → 关联后轻量提示态（不消失）→ 可关闭；
 * 5. 「可导入」徽章一次性：勾选或点击后本会话不再显示；
 * 6. completeTransferCount 与 categorizeRow 同口径（转账+重复归 duplicate 卡，
 *    不计入数据完整卡的 chips）。
 */

const mocks = vi.hoisted(() => ({
  saveDraft: vi.fn(),
  getDraftWithSet: vi.fn(),
  discardDraft: vi.fn(),
  confirmImportApi: vi.fn(),
  runReconciliation: vi.fn(),
  getLedgers: vi.fn(),
  elMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
    info: vi.fn()
  }
}));

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: vi.fn() })
}));

vi.mock("element-plus", () => ({
  ElMessage: mocks.elMessage,
  ElMessageBox: { confirm: vi.fn() }
}));

vi.mock("@/composables/useReconDraft", () => ({
  useReconDraft: () => ({
    saveDraft: mocks.saveDraft,
    getDraftWithSet: mocks.getDraftWithSet,
    discardDraft: mocks.discardDraft
  })
}));

vi.mock("@/composables/useNavCache", () => ({
  navCache: { getNavs: vi.fn() }
}));

vi.mock("@/api/importer", () => ({
  parseFile: vi.fn(),
  confirmImport: mocks.confirmImportApi
}));

vi.mock("@/api/reconciliation", () => ({
  runReconciliation: mocks.runReconciliation
}));

vi.mock("@/api/ledger", () => ({
  getLedgers: mocks.getLedgers,
  createLedger: vi.fn(),
  updateLedger: vi.fn(),
  getSalesInstitutions: vi.fn()
}));

/** 一条正常预览行 */
function makeNormalRow() {
  return {
    symbol: "600519",
    name: "贵州茅台",
    op_type: "buy",
    trade_date: "2026-03-12",
    quantity: 100,
    price: 1680.5,
    amount: 168050,
    type: "stock"
  };
}

/** 一条银证转账行（quantity/price 为 0 是正常形态，isRowBlocked 对其放行） */
function makeTransferRow(overrides: Record<string, unknown> = {}) {
  return {
    symbol: "__CASH__",
    name: "银行转证券",
    op_type: "deposit",
    trade_date: "2026-03-12",
    quantity: 0,
    price: 0,
    amount: 10000,
    type: "cash",
    is_cash_transfer: true,
    ...overrides
  };
}

/**
 * 装配向导：证券账户 + 现金账户；linked=true 时给证券账户关联现金账户。
 * 返回 [正常行, 转账行]。
 */
function setupWizard(linked: boolean) {
  const w = useImportWizard();
  w.ledgers.value = [
    {
      id: 1,
      name: "测试证券账户",
      ledger_type: "stock",
      default_allocation: "longterm",
      linked_cash_ledger_id: linked ? 2 : null
    },
    { id: 2, name: "测试现金账户", ledger_type: "bank" }
  ] as never;
  w.selectedLedgerId.value = 1;
  w.currentStep.value = 2;
  const rows = w.addRowKeys([makeNormalRow(), makeTransferRow()]);
  w.previewData.value = rows;
  return { w, rows };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.saveDraft.mockResolvedValue(undefined);
  mocks.getDraftWithSet.mockResolvedValue(null);
  mocks.discardDraft.mockResolvedValue(undefined);
  mocks.confirmImportApi.mockResolvedValue({
    data: { imported: 1, skipped: 0, cash_transfers_created: 1 }
  });
  mocks.runReconciliation.mockResolvedValue(undefined);
  mocks.getLedgers.mockResolvedValue([]);
});

describe("#2281 转账行勾选：条件放开", () => {
  it("未关联现金账户：转账行不可勾（isRowSelectable=false），正常行可勾", () => {
    const { w, rows } = setupWizard(false);
    expect(w.isRowSelectable(rows[1])).toBe(false);
    expect(w.isRowSelectable(rows[0])).toBe(true);
  });

  it("已关联现金账户：转账行可勾（isRowSelectable=true）", () => {
    const { w, rows } = setupWizard(true);
    expect(w.isRowSelectable(rows[1])).toBe(true);
  });
});

describe("#2281 可勾但不默认勾：批量动作不纳入转账行", () => {
  it("selectAllValid 不勾转账行（未关联 / 已关联两种状态下均不勾）", () => {
    for (const linked of [false, true]) {
      const { w, rows } = setupWizard(linked);
      w.selectAllValid();
      expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(true);
      expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(false);
    }
  });

  it("卡片批量勾选「数据完整」不纳入转账行", () => {
    const { w, rows } = setupWizard(true);
    w.toggleCategorySelection("complete", true);
    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(true);
    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(false);
  });

  it("卡片取消「数据完整」走宽口径：手动勾上的转账行一并清除", () => {
    const { w, rows } = setupWizard(true);
    w.handleRowCheckboxChange(rows[1], true); // 用户显式勾选转账行
    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(true);

    w.toggleCategorySelection("complete", false);

    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(false);
    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(false);
  });

  it("手动勾选的转账行进入导入载荷（能勾 = 能导）", async () => {
    const { w, rows } = setupWizard(true);
    w.selectAllValid();
    w.handleRowCheckboxChange(rows[1], true);

    await w.confirmImport();

    expect(mocks.confirmImportApi).toHaveBeenCalledTimes(1);
    const payload = mocks.confirmImportApi.mock.calls[0][0] as Array<
      Record<string, unknown>
    >;
    expect(payload).toHaveLength(2);
    const transfer = payload.find(r => r._rowKey === rows[1]._rowKey);
    expect(transfer).toBeDefined();
    expect(transfer?.is_cash_transfer).toBe(true);
  });

  it("卡片三态：手动勾选转账行后「数据完整」卡显示 some（与表格可见勾选一致）", () => {
    const { w, rows } = setupWizard(true);
    expect(w.categoryCheckState("complete")).toBe("none");
    w.handleRowCheckboxChange(rows[1], true);
    expect(w.categoryCheckState("complete")).toBe("some");
  });
});

describe("#2281 横幅双态：关联后不消失、可关闭", () => {
  it("未关联：显示引导态，不显示轻量提示态", () => {
    const { w } = setupWizard(false);
    expect(w.showCashBindingBanner.value).toBe(true);
    expect(w.showCashTransferHint.value).toBe(false);
  });

  it("已关联：引导态消失、轻量提示态出现（修复关联后提示全无的断点）", () => {
    const { w } = setupWizard(true);
    expect(w.showCashBindingBanner.value).toBe(false);
    expect(w.showCashTransferHint.value).toBe(true);
    expect(w.linkedCashLedgerName.value).toBe("测试现金账户");
  });

  it("关闭轻量提示态后两种横幅都不显示；新会话装新数据后重现", () => {
    const { w } = setupWizard(true);
    w.dismissCashBindingBanner();
    expect(w.showCashTransferHint.value).toBe(false);

    // 新导入会话：clearImportState 重置 dismiss 态，换文件重新解析出转账行
    w.clearImportState();
    expect(w.showCashTransferHint.value).toBe(false); // 暂无数据
    w.previewData.value = w.addRowKeys([makeNormalRow(), makeTransferRow()]);
    expect(w.showCashTransferHint.value).toBe(true);
  });

  it("无转账行时两种横幅都不显示", () => {
    const w = useImportWizard();
    w.ledgers.value = [
      { id: 1, name: "证券", ledger_type: "stock", linked_cash_ledger_id: 2 },
      { id: 2, name: "现金", ledger_type: "bank" }
    ] as never;
    w.selectedLedgerId.value = 1;
    w.currentStep.value = 2;
    w.previewData.value = w.addRowKeys([makeNormalRow()]);
    expect(w.showCashBindingBanner.value).toBe(false);
    expect(w.showCashTransferHint.value).toBe(false);
  });
});

describe("#2281 「可导入」徽章：一次性提示", () => {
  it("转账行初始显示徽章；dismiss 后消失；正常行从不显示", () => {
    const { w, rows } = setupWizard(true);
    expect(w.showTransferBadge(rows[1])).toBe(true);
    expect(w.showTransferBadge(rows[0])).toBe(false);

    w.dismissTransferBadge(rows[1]);
    expect(w.showTransferBadge(rows[1])).toBe(false);
  });

  it("徽章 dismiss 态按行记录： dismiss 一行不影响另一行", () => {
    const { w } = setupWizard(true);
    const rows2 = w.addRowKeys([makeTransferRow()]);
    w.previewData.value = [...w.previewData.value, ...rows2];
    w.dismissTransferBadge(rows2[0]);
    expect(w.showTransferBadge(rows2[0])).toBe(false);
    expect(w.showTransferBadge(w.previewData.value[1])).toBe(true);
  });
});

describe("#2281 摘要 chips 计数：与 categorizeRow 同口径", () => {
  it("纯转账行计入 completeTransferCount", () => {
    const { w } = setupWizard(true);
    expect(w.completeTransferCount.value).toBe(1);
  });

  it("转账行同时疑似重复时归 duplicate 卡，不计入 chips", () => {
    const { w } = setupWizard(true);
    w.previewData.value = w.addRowKeys([
      makeTransferRow({ is_duplicate: true })
    ]);
    expect(w.completeTransferCount.value).toBe(0);
    expect(w.summaryCounts.value.duplicate).toBe(1);
    expect(w.summaryCounts.value.complete).toBe(0);
  });

  it("chips 计数恒不超过「数据完整」卡条数（子集不变量）", () => {
    const { w } = setupWizard(true);
    w.previewData.value = w.addRowKeys([
      makeNormalRow(),
      makeTransferRow(),
      makeTransferRow({ is_duplicate: true })
    ]);
    expect(w.completeTransferCount.value).toBe(1);
    expect(w.completeTransferCount.value).toBeLessThanOrEqual(
      w.summaryCounts.value.complete
    );
  });
});
