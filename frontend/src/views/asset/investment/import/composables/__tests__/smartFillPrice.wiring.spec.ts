import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";
import type { OcrTxnRow } from "@/api/ocr";

/**
 * #2903 的**接线层**回归：纯函数口径对不代表两条通道真的用了它。
 *
 * 历史教训（AGENTS.md「守门要分两层，组件层抓不到宿主没接线」）：组件/纯函数层断言
 * 全绿，宿主却根本没读它的判定——问题出在接线上，不在被测单元。本卡尤其容易复发的
 * 形态就是「谓词写好了、某条通道仍然手抄一份计算式」，故这里驱动真实 composable：
 *
 * 1. OCR 通道（`onAiRowsFound`）：普通缺价行被补价，税额行不被补；
 * 2. 补价后该行进入自动勾选——即补价不是纯展示，它改变「能不能导入」。
 *
 * 文件上传通道（`handleUpload`）的接线由静态守卫
 * `scripts/guard_smart_fill_parity.mjs` 覆盖：它逐字扫两处调用点，禁止再手写补价计算式。
 */

const mocks = vi.hoisted(() => ({
  saveDraft: vi.fn(),
  getDraftWithSet: vi.fn(),
  discardDraft: vi.fn(),
  getLedgers: vi.fn()
}));

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: vi.fn() })
}));

vi.mock("element-plus", () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
    info: vi.fn()
  },
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

beforeEach(() => {
  vi.clearAllMocks();
  mocks.saveDraft.mockResolvedValue(undefined);
  mocks.getDraftWithSet.mockResolvedValue(null);
  mocks.discardDraft.mockResolvedValue(undefined);
  mocks.getLedgers.mockResolvedValue([]);
});

/** OCR 通道的输入是 OcrTxnRow（不是预览行）：按入口契约造完整夹具 */
function ocrRow(patch: Partial<OcrTxnRow> = {}): OcrTxnRow {
  return {
    symbol: "000001",
    name: "测试标的",
    type: "fund",
    display_type: "基金",
    op_type: "buy",
    op_type_label: "买入",
    quantity: 100,
    price: 0,
    amount: 1234,
    fee: 0,
    trade_date: "2026-03-12",
    import_hash: "ocr-test",
    source: "ocr",
    is_duplicate: false,
    error: null,
    warnings: [],
    ...patch
  };
}

describe("OCR 通道接线（onAiRowsFound）", () => {
  it("普通缺价行：补出单价并标记 smartFilled", () => {
    const w = useImportWizard();
    w.onAiRowsFound([ocrRow()]);

    const row = w.previewData.value[0];
    expect(row.price).toBe(12.34);
    expect(row.smartFilled).toBe(true);
  });

  it("税额行（tax）：金额是税额不是成交额，不补价", () => {
    const w = useImportWizard();
    // 金额取正数：让「类型排除」这条判据独立于「金额非正」那条，任一条漏了都会红
    w.onAiRowsFound([ocrRow({ op_type: "tax", quantity: 60, amount: 18 })]);

    expect(w.previewData.value[0].price).toBe(0);
    expect(w.previewData.value[0].smartFilled).toBeUndefined();
  });

  it("补价后该行被自动勾选（补价改变「能不能导入」，不是纯展示）", () => {
    const w = useImportWizard();
    w.onAiRowsFound([ocrRow()]);

    const row = w.previewData.value[0];
    expect(w.selectedKeys.value.has(row._rowKey)).toBe(true);
    expect(w.categorizeRow(row)).toBe("complete");
  });

  it("解析错误行：不补价、不被勾选（脏行不因补价变得可导入）", () => {
    const w = useImportWizard();
    w.onAiRowsFound([ocrRow({ error: "无法识别" })]);

    const row = w.previewData.value[0];
    expect(row.price).toBe(0);
    expect(w.selectedKeys.value.has(row._rowKey)).toBe(false);
  });
});
