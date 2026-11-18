import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";

/**
 * #2281：放开银证转账行导入勾选 + 三层感知的回归测试。
 *
 * 被测不变量（本期核心契约）：
 * 1. 转账行可勾选取决于现金账户关联状态：未关联禁用（isRowSelectable=false），
 *    已关联放开（isRowSelectable=true）——「能勾 = 能导」；
 * 2. 批量动作不纳入转账行：selectAllValid / 卡片批量勾选 / importNormalOnly
 *    均不勾转账行（#2281 语义）；默认态时点（预览初始化 / 匹配完成 / 关联落库）
 *    由 preselectTransferRows 幂等补齐（2026-11-08 导入完整性取向，见文末一组）；
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
  updateLedger: vi.fn(),
  elMessageBoxConfirm: vi.fn(),
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
  ElMessageBox: { confirm: mocks.elMessageBoxConfirm }
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
  updateLedger: mocks.updateLedger,
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
  mocks.updateLedger.mockResolvedValue({ data: { id: 1 } });
  mocks.elMessageBoxConfirm.mockResolvedValue(undefined);
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

/*
 * #2838：原「可导入」徽章已移除（勾选列只有 50px，必然折行并被截成「可导…」；
 * 而它要说的「转账行能导」已由状态列 / 可勾的复选框 / 页顶横幅三处重复表达）。
 * 批量层面改由摘要卡旁的「全部勾选」承担——下面这批用例守的就是那个入口。
 */
describe("#2838 转账行批量勾选：全部勾选 / 全部取消", () => {
  it("一次点上：作用域内的转账行全入选中，已勾的正常行不受影响", () => {
    const { w, rows } = setupWizard(true);
    w.selectAllValid();
    expect(w.transferRowsAllSelected.value).toBe(false);

    w.toggleAllTransferRows();

    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(true);
    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(true);
    expect(w.transferRowsAllSelected.value).toBe(true);
  });

  it("再点一次：只清转账行，正常行的勾选保留（不是清空重来）", () => {
    const { w, rows } = setupWizard(true);
    w.selectAllValid();
    w.toggleAllTransferRows();

    w.toggleAllTransferRows();

    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(false);
    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(true);
    expect(w.transferRowsAllSelected.value).toBe(false);
  });

  it("作用域 = 摘要卡那个 N：疑似重复的转账行不在内（#1882 需手动勾）", () => {
    const w = useImportWizard();
    const rows = w.addRowKeys([
      makeTransferRow(),
      makeTransferRow({ trade_date: "2026-03-13" }),
      makeTransferRow({ trade_date: "2026-03-14", is_duplicate: true })
    ]);
    w.ledgers.value = [
      {
        id: 1,
        name: "测试证券账户",
        ledger_type: "stock",
        default_allocation: "longterm",
        linked_cash_ledger_id: 2
      },
      { id: 2, name: "测试现金账户", ledger_type: "bank" }
    ] as never;
    w.selectedLedgerId.value = 1;
    w.previewData.value = rows;

    expect(w.completeTransferCount.value).toBe(2);
    w.toggleAllTransferRows();

    expect(w.selectedKeys.value.size).toBe(2);
    expect(w.selectedKeys.value.has(rows[2]._rowKey)).toBe(false);
  });

  it("未关联现金账户时不动作：不勾出一批「勾了也导不进去」的行", () => {
    const { w, rows } = setupWizard(false);
    w.toggleAllTransferRows();
    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(false);
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

/*
 * 2026-11-08 取向变更：#2281 的「默认不勾」只在**批量动作**层面保留，
 * 默认态层面改为「导入即完整」——用户实测 99 条转账默认漏导后证券账户
 * 资金流断裂、对账必出孤儿。默认勾选的前置条件是已关联现金账户；
 * 疑似重复的转账行仍归 duplicate 卡、留给用户手动决定。
 * 批量动作（selectAllValid / 卡片勾选 / importNormalOnly）的 #2281 语义
 * 由上面那组用例继续看守，两取向并存不冲突。
 */
describe("2026-11-08 导入完整性：默认态时点转账行自动补齐", () => {
  it("preselectTransferRows：已关联时补齐 complete 转账行，正常行不受影响", () => {
    const { w, rows } = setupWizard(true);
    w.selectAllValid();
    // 前置：批量动作不勾转账行（#2281 语义不变）
    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(false);

    w.preselectTransferRows();

    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(true);
    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(true);
  });

  it("幂等：重复调用不翻转、已勾的行不丢失", () => {
    const { w, rows } = setupWizard(true);
    w.selectAllValid();
    w.preselectTransferRows();
    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(true);
    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(true);
    w.preselectTransferRows();
    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(true);
    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(true);
  });

  it("未关联时是空操作：不勾出一批「勾了也导不进去」的行", () => {
    const { w, rows } = setupWizard(false);
    w.selectAllValid();
    w.preselectTransferRows();
    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(false);
  });

  it("疑似重复的转账行不补勾（归 duplicate 卡，#1882 手动决定不变）", () => {
    const { w } = setupWizard(true);
    w.previewData.value = w.addRowKeys([
      makeNormalRow(),
      makeTransferRow({ is_duplicate: true })
    ]);
    w.selectAllValid();
    w.preselectTransferRows();
    const dupTransfer = w.previewData.value.find(r => r.is_duplicate);
    expect(w.selectedKeys.value.has(dupTransfer!._rowKey)).toBe(false);
  });

  it("端到端判据：默认态直接确认导入，转账行进载荷（对账完整的最终形态）", async () => {
    const { w, rows } = setupWizard(true);
    w.selectAllValid();
    w.preselectTransferRows();
    await w.confirmImport();

    const payload = mocks.confirmImportApi.mock.calls[0][0] as Array<
      Record<string, unknown>
    >;
    expect(payload).toHaveLength(2);
    expect(payload.some(r => r._rowKey === rows[1]._rowKey)).toBe(true);
  });
});

/*
 * 2026-11-08 关联落库前确认：默认勾选转账行后，关联错账本的代价升级为
 * 「N 条反向流水写进错误账本」，必须在写库前让用户看见条数与后果。
 */
describe("2026-11-08 关联落库前确认：条数与后果前置可见", () => {
  it("下拉选择关联：先弹确认（含转账条数），确认后才落库并补勾", async () => {
    const { w, rows } = setupWizard(false);
    w.bannerCashLedgerId.value = 2;
    // 落库后 fetchLedgers 重新拉取：返回已关联状态（否则补勾 guard 会挡住）
    mocks.getLedgers.mockResolvedValue({
      data: [
        {
          id: 1,
          name: "测试证券账户",
          ledger_type: "stock",
          linked_cash_ledger_id: 2
        },
        { id: 2, name: "测试现金账户", ledger_type: "bank" }
      ]
    });
    await w.linkCashAccount();

    expect(mocks.elMessageBoxConfirm).toHaveBeenCalledTimes(1);
    const [detail] = mocks.elMessageBoxConfirm.mock.calls[0] as [string];
    expect(detail).toContain("1 条银证转账");
    expect(detail).toContain("测试现金账户");
    expect(mocks.updateLedger).toHaveBeenCalledTimes(1);
    // 落库成功后按默认态补勾转账行
    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(true);
  });

  it("用户取消确认：不落库、清空下拉选择、不补勾", async () => {
    const { w, rows } = setupWizard(false);
    w.bannerCashLedgerId.value = 2;
    mocks.elMessageBoxConfirm.mockRejectedValueOnce("cancel");
    await w.linkCashAccount();

    expect(mocks.updateLedger).not.toHaveBeenCalled();
    expect(w.bannerCashLedgerId.value).toBeNull();
    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(false);
  });

  it("skipConfirm（新建现金账户链路）：不弹确认直接落库", async () => {
    const { w } = setupWizard(false);
    w.bannerCashLedgerId.value = 2;
    await w.linkCashAccount({ skipConfirm: true });

    expect(mocks.elMessageBoxConfirm).not.toHaveBeenCalled();
    expect(mocks.updateLedger).toHaveBeenCalledTimes(1);
  });
});
