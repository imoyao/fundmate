import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";
import { navCache } from "@/composables/useNavCache";

/**
 * #783 终审遗留小问题修复的回归测试（2026-10-17 复核结论落地）。
 *
 * 被测不变量：
 * 1. 净值填充推算份额统一 toFixed(4) 修边——fetchAndFillFundNav（autoFix 路径）
 *    与 fillNavForRecords（smartFill 路径）口径一致，长浮点不进表格；
 * 2. 恢复忽略行 = 回到全选默认态：谓词内（isAutoSelectableRow）的行重新勾上，
 *    疑似重复 / 解析错误 / 待补全 / 资金划转行不因此被勾（#1882）；
 * 3. 草稿恢复前校验账户存在性：账户已删除则拒绝恢复 + 丢弃草稿 + 明确提示，
 *    不再带着死 ledgerId 走到 confirmImport 才失败；fetch 失败空列表不误判。
 */

const mocks = vi.hoisted(() => ({
  saveDraft: vi.fn(),
  getDraftWithSet: vi.fn(),
  discardDraft: vi.fn(),
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
  confirmImport: vi.fn()
}));

vi.mock("@/api/reconciliation", () => ({
  runReconciliation: vi.fn()
}));

vi.mock("@/api/ledger", () => ({
  getLedgers: mocks.getLedgers,
  createLedger: vi.fn(),
  updateLedger: vi.fn(),
  getSalesInstitutions: vi.fn()
}));

/** 构造一行完整可导入的预览行 */
function makeRow(overrides: Record<string, unknown> = {}) {
  return {
    symbol: "600519",
    name: "贵州茅台",
    op_type: "buy",
    trade_date: "2026-03-12",
    quantity: 100,
    price: 1680.5,
    amount: 168050,
    type: "stock",
    ...overrides
  };
}

/** 缺净值/份额的基金行：命中两条净值填充路径的同一过滤条件 */
function makeFundRow(overrides: Record<string, unknown> = {}) {
  return makeRow({
    type: "fund",
    symbol: "000001",
    name: "华夏成长",
    price: 0,
    quantity: 0,
    amount: 100,
    ...overrides
  });
}

function makeLedger(id: number) {
  return {
    id,
    name: `账户${id}`,
    ledger_type: "stock",
    default_allocation: "longterm"
  } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.saveDraft.mockResolvedValue(undefined);
  mocks.getDraftWithSet.mockResolvedValue(null);
  mocks.discardDraft.mockResolvedValue(undefined);
  mocks.getLedgers.mockResolvedValue([]);
});

describe("净值填充：份额统一 toFixed(4) 修边", () => {
  it("fetchAndFillFundNav：100 元 / 净值 3 → 份额 33.3333（长浮点被修掉）", async () => {
    vi.mocked(navCache.getNavs).mockResolvedValue({ "000001": 3 });
    const w = useImportWizard();
    const rows = w.addRowKeys([makeFundRow()]);
    w.previewData.value = rows;

    await w.fetchAndFillFundNav();

    expect(rows[0].price).toBe(3);
    expect(rows[0].quantity).toBe(33.3333);
    expect(rows[0].is_calculated).toBe(true);
  });

  it("fillNavForRecords（smartFill 路径）：同一修边口径", async () => {
    vi.mocked(navCache.getNavs).mockResolvedValue({ "000001": 3 });
    const w = useImportWizard();
    const rows = w.addRowKeys([makeFundRow()]);
    w.previewData.value = rows;

    await w.fillNavForRecords(rows);

    expect(rows[0].quantity).toBe(33.3333);
  });

  it("fillNavForRecords：净值缺失时置 price=0 并标记待补全（不静默算错）", async () => {
    vi.mocked(navCache.getNavs).mockResolvedValue({});
    const w = useImportWizard();
    const rows = w.addRowKeys([makeFundRow()]);
    w.previewData.value = rows;

    await w.fillNavForRecords(rows);

    expect(rows[0].price).toBe(0);
    expect(rows[0]._dataMissing).toBe(true);
    expect(rows[0].is_calculated).toBe(false);
  });
});

describe("toggleIgnoreRow：恢复忽略 = 回到全选默认态", () => {
  it("普通行：忽略取消勾选，恢复后重新勾上", () => {
    const w = useImportWizard();
    const rows = w.addRowKeys([makeRow()]);
    w.previewData.value = rows;
    w.selectAllValid();
    expect(w.selectedKeys.value.size).toBe(1);

    w.toggleIgnoreRow(rows[0]); // 忽略
    expect(rows[0]._ignored).toBe(true);
    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(false);

    w.toggleIgnoreRow(rows[0]); // 恢复
    expect(rows[0]._ignored).toBe(false);
    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(true);
  });

  it("疑似重复行：恢复后不自动勾（要导仍需手动勾，#1882）", () => {
    const w = useImportWizard();
    const rows = w.addRowKeys([makeRow({ is_duplicate: true })]);
    w.previewData.value = rows;

    w.toggleIgnoreRow(rows[0]);
    w.toggleIgnoreRow(rows[0]);

    expect(rows[0]._ignored).toBe(false);
    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(false);
  });

  it("解析错误行：恢复后不勾（本就不可勾）", () => {
    const w = useImportWizard();
    const rows = w.addRowKeys([makeRow({ error: "解析失败: 测试" })]);
    w.previewData.value = rows;

    w.toggleIgnoreRow(rows[0]);
    w.toggleIgnoreRow(rows[0]);

    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(false);
  });

  it("资金划转行：恢复后不勾（不可导入）", () => {
    const w = useImportWizard();
    const rows = w.addRowKeys([makeRow({ is_cash_transfer: true })]);
    w.previewData.value = rows;

    w.toggleIgnoreRow(rows[0]);
    w.toggleIgnoreRow(rows[0]);

    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(false);
  });

  it("数量价格缺失行：恢复后不勾（isRowBlocked）", () => {
    const w = useImportWizard();
    const rows = w.addRowKeys([makeRow({ quantity: 0, price: 0 })]);
    w.previewData.value = rows;

    w.toggleIgnoreRow(rows[0]);
    w.toggleIgnoreRow(rows[0]);

    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(false);
  });

  it("忽略中的行不参与 selectAllValid（谓词共用不变量）", () => {
    const w = useImportWizard();
    const rows = w.addRowKeys([makeRow(), makeRow({ symbol: "000858" })]);
    w.previewData.value = rows;

    w.toggleIgnoreRow(rows[1]); // 忽略第二行
    w.selectAllValid();

    expect(w.selectedKeys.value.has(rows[0]._rowKey)).toBe(true);
    expect(w.selectedKeys.value.has(rows[1]._rowKey)).toBe(false);
  });
});

describe("restoreDraft：账户存在性前置校验", () => {
  function makeDraft(overrides: Record<string, unknown> = {}) {
    return {
      domain: "C",
      ledgerId: 1,
      selectedLedgerId: 1,
      savedAt: new Date().toISOString(),
      currentStep: 2,
      selectedMode: "standard_fund",
      rows: [makeRow()],
      selectedKeys: [],
      selectedKeySet: new Set<string>(),
      ...overrides
    };
  }

  it("账户存在：正常恢复并回填 selectedLedgerId", async () => {
    mocks.getDraftWithSet.mockResolvedValueOnce(makeDraft());
    const w = useImportWizard();
    w.ledgers.value = [makeLedger(1)];

    await w.restoreDraft();

    expect(w.selectedLedgerId.value).toBe(1);
    expect(w.currentStep.value).toBe(2);
    expect(mocks.discardDraft).not.toHaveBeenCalled();
  });

  it("账户已删除：拒绝恢复 + 丢弃草稿 + 警告提示，不带着死 ledgerId 前进", async () => {
    mocks.getDraftWithSet.mockResolvedValueOnce(
      makeDraft({ selectedLedgerId: 999, ledgerId: 999 })
    );
    const w = useImportWizard();
    w.ledgers.value = [makeLedger(1)];

    await w.restoreDraft();

    expect(mocks.discardDraft).toHaveBeenCalledTimes(1);
    expect(mocks.elMessage.warning).toHaveBeenCalledWith(
      expect.stringContaining("账户已被删除")
    );
    // 没有恢复任何状态：步骤、数据、勾选均不动
    expect(w.selectedLedgerId.value).toBeNull();
    expect(w.currentStep.value).toBe(0);
    expect(w.previewData.value).toHaveLength(0);
    expect(w.draftBannerVisible.value).toBe(false);
  });

  it("账户列表为空（fetch 失败形态）：不误判失效，照常恢复", async () => {
    mocks.getDraftWithSet.mockResolvedValueOnce(
      makeDraft({ selectedLedgerId: 7 })
    );
    const w = useImportWizard();
    // ledgers 保持默认空数组（fetchLedgers 失败时的形态）

    await w.restoreDraft();

    expect(w.selectedLedgerId.value).toBe(7);
    expect(w.currentStep.value).toBe(2);
    expect(mocks.discardDraft).not.toHaveBeenCalled();
  });

  it("草稿无账户上下文（selectedLedgerId 为 null）：不触发校验，正常恢复", async () => {
    mocks.getDraftWithSet.mockResolvedValueOnce(
      makeDraft({ selectedLedgerId: null, ledgerId: null })
    );
    const w = useImportWizard();
    w.ledgers.value = [makeLedger(1)];

    await w.restoreDraft();

    expect(w.selectedLedgerId.value).toBeNull();
    expect(w.currentStep.value).toBe(2);
    expect(mocks.discardDraft).not.toHaveBeenCalled();
  });
});
