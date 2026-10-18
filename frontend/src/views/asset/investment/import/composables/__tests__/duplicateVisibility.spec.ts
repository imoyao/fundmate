import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";

/**
 * #2274：「取消显示重复行」显隐与勾选解耦的回归测试。
 *
 * 被测不变量（修复的核心契约）：
 * 1. 隐藏/恢复重复行只改显隐，绝不清空 selectedKeys——导入载荷与
 *    「已选择 N 条」均以 selectedKeys 为唯一真相源；
 * 2. 隐藏但仍勾选的重复行继续进入导入载荷（keep_duplicate 真插入），
 *    并由 hiddenSelectedDuplicateCount 暴露给 UI；
 * 3. 草稿恢复后 duplicatesHandled 开关与行级隐藏标记一致（按钮不撒谎）。
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

/** 构造一行完整可导入的预览行（数量/价格/金额齐备，不被 isRowBlocked 拦下） */
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

/** 一条正常行 + 一条疑似重复行；返回带 _rowKey 的行数组 */
function setupPreview(w: ReturnType<typeof useImportWizard>) {
  const rows = w.addRowKeys([makeRow(), makeRow({ is_duplicate: true })]);
  w.previewData.value = rows;
  w.duplicateCount.value = 1;
  return rows;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.saveDraft.mockResolvedValue(undefined);
  mocks.getDraftWithSet.mockResolvedValue(null);
  mocks.discardDraft.mockResolvedValue(undefined);
  mocks.confirmImportApi.mockResolvedValue({
    data: { imported: 1, skipped: 0, kept_duplicates: 1 }
  });
  mocks.runReconciliation.mockResolvedValue(undefined);
  mocks.getLedgers.mockResolvedValue([]);
});

describe("#2274 deselectAllDuplicates：显隐与勾选解耦", () => {
  it("取消显示重复行不再清除勾选（核心回归：修复前会静默删除）", () => {
    const w = useImportWizard();
    const rows = setupPreview(w);
    const dupKey = rows[1]._rowKey;

    // 用户手动勾选保留这条重复行（默认 selectAllValid 不选重复行）
    w.handleRowCheckboxChange(rows[1], true);
    expect(w.selectedKeys.value.has(dupKey)).toBe(true);
    expect(w.selectedCount.value).toBe(1);

    w.deselectAllDuplicates();

    // 行被隐藏，但勾选原样保留、计数不变
    expect(rows[1]._duplicateHandled).toBe(true);
    expect(w.duplicatesHandled.value).toBe(true);
    expect(w.selectedKeys.value.has(dupKey)).toBe(true);
    expect(w.selectedCount.value).toBe(1);
  });

  it("恢复查看重复行后，此前保留的勾选仍在（修复前恢复不还原）", () => {
    const w = useImportWizard();
    const rows = setupPreview(w);
    const dupKey = rows[1]._rowKey;

    w.handleRowCheckboxChange(rows[1], true);
    w.deselectAllDuplicates(); // 隐藏
    w.deselectAllDuplicates(); // 恢复查看

    expect(rows[1]._duplicateHandled).toBe(false);
    expect(w.duplicatesHandled.value).toBe(false);
    expect(w.selectedKeys.value.has(dupKey)).toBe(true);
    expect(w.selectedCount.value).toBe(1);
  });

  it("隐藏时若有勾选的重复行，成功文案明示仍将参与导入", () => {
    const w = useImportWizard();
    const rows = setupPreview(w);
    w.handleRowCheckboxChange(rows[1], true);

    w.deselectAllDuplicates();

    expect(mocks.elMessage.success).toHaveBeenCalledWith(
      expect.stringContaining("仍将参与导入")
    );
  });

  it("隐藏时没有勾选的重复行，文案不出现误导性补充", () => {
    const w = useImportWizard();
    setupPreview(w); // 重复行未勾选

    w.deselectAllDuplicates();

    const msg = mocks.elMessage.success.mock.calls[0]?.[0] as string;
    expect(msg).toContain("已取消 1 条重复数据的展示");
    expect(msg).not.toContain("仍将参与导入");
  });
});

describe("#2274 hiddenSelectedDuplicateCount", () => {
  it("仅在「已隐藏且仍勾选」时计数，恢复或未勾选均为 0", () => {
    const w = useImportWizard();
    const rows = setupPreview(w);

    // 未隐藏 → 0
    expect(w.hiddenSelectedDuplicateCount.value).toBe(0);

    // 隐藏但未勾选 → 0
    w.deselectAllDuplicates();
    expect(w.hiddenSelectedDuplicateCount.value).toBe(0);

    // 手动勾选后 → 1（全部数据视图下重复行可见，仍可勾选）
    w.handleRowCheckboxChange(rows[1], true);
    expect(w.hiddenSelectedDuplicateCount.value).toBe(1);

    // 取消勾选 → 0
    w.handleRowCheckboxChange(rows[1], false);
    expect(w.hiddenSelectedDuplicateCount.value).toBe(0);

    // 重新勾选后恢复查看 → 0
    w.handleRowCheckboxChange(rows[1], true);
    w.deselectAllDuplicates();
    expect(w.hiddenSelectedDuplicateCount.value).toBe(0);
  });
});

describe("#2274 导入载荷：隐藏不丢行", () => {
  it("隐藏的已勾选重复行仍进入导入载荷，并带 keep_duplicate 标记", async () => {
    const w = useImportWizard();
    w.ledgers.value.push({
      id: 1,
      name: "测试账户",
      ledger_type: "stock",
      default_allocation: "longterm"
    } as never);
    w.selectedLedgerId.value = 1;

    const rows = setupPreview(w);
    w.selectAllValid(); // 选中正常行
    w.handleRowCheckboxChange(rows[1], true); // 手动保留重复行
    w.deselectAllDuplicates(); // 隐藏（修复后勾选保留）

    await w.confirmImport();

    expect(mocks.confirmImportApi).toHaveBeenCalledTimes(1);
    const payload = mocks.confirmImportApi.mock.calls[0][0] as Array<
      Record<string, unknown>
    >;
    // 两行都在载荷里：正常行 + 隐藏但已勾选的重复行
    expect(payload).toHaveLength(2);
    const kept = payload.find(r => r._rowKey === rows[1]._rowKey);
    expect(kept).toBeDefined();
    expect(kept?.keep_duplicate).toBe(true);
    // 正常行不带 keep_duplicate
    const normal = payload.find(r => r._rowKey === rows[0]._rowKey);
    expect(normal?.keep_duplicate).toBeUndefined();
  });
});

describe("#2274 草稿恢复：开关与行级隐藏标记一致", () => {
  it("草稿中的重复行带隐藏标记 → 恢复后 duplicatesHandled 为 true（按钮显示恢复查看）", async () => {
    mocks.getDraftWithSet.mockResolvedValueOnce({
      domain: "C",
      ledgerId: 1,
      savedAt: new Date().toISOString(),
      currentStep: 2,
      selectedMode: "standard_fund",
      rows: [
        makeRow(),
        makeRow({ is_duplicate: true, _duplicateHandled: true })
      ],
      selectedKeys: ["row_1"],
      selectedKeySet: new Set(["row_1"])
    });

    const w = useImportWizard();
    await w.restoreDraft();

    expect(w.duplicatesHandled.value).toBe(true);
    // 勾选随草稿恢复，隐藏行仍被勾选 → 提示计数为 1
    expect(w.selectedKeys.value.has("row_1")).toBe(true);
    expect(w.hiddenSelectedDuplicateCount.value).toBe(1);
  });

  it("草稿中无隐藏标记 → 恢复后 duplicatesHandled 为 false", async () => {
    mocks.getDraftWithSet.mockResolvedValueOnce({
      domain: "C",
      ledgerId: 1,
      savedAt: new Date().toISOString(),
      currentStep: 2,
      selectedMode: "standard_fund",
      rows: [makeRow(), makeRow({ is_duplicate: true })],
      selectedKeys: [],
      selectedKeySet: new Set()
    });

    const w = useImportWizard();
    await w.restoreDraft();

    expect(w.duplicatesHandled.value).toBe(false);
  });
});
