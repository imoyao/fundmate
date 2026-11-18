import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";

/**
 * #2854 导入行数对账的行为契约。
 *
 * 旧实现里预览 `total` 是「已经丢过行的数」，未知操作名整行静默消失，
 * 用户连对账的锚点都没有。这里钉住 computed 的四条判据：
 * 1. 非文件通道（AI 识别 / 草稿）没有源文件行数 → 不显示；
 * 2. 零差异零失败 → 不打扰；
 * 3. 有未知操作名 → 差额、操作名、恒等式都要能直接写出来；
 * 4. 恒等式不成立 → 必须标记「对不平」，不能假装一切正常。
 */

const mocks = vi.hoisted(() => ({
  saveDraft: vi.fn(),
  getDraftWithSet: vi.fn(),
  discardDraft: vi.fn(),
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
  getLedgers: vi.fn(),
  createLedger: vi.fn(),
  updateLedger: vi.fn(),
  getSalesInstitutions: vi.fn()
}));

function setup() {
  return useImportWizard();
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.saveDraft.mockResolvedValue(undefined);
  mocks.getDraftWithSet.mockResolvedValue(null);
  mocks.discardDraft.mockResolvedValue(undefined);
});

describe("#2854 导入行数对账", () => {
  it("源文件行数未知（AI 识别通道）→ 不显示对账", () => {
    const w = setup();
    expect(w.sourceRowCount.value).toBeNull();
    expect(w.rowReconciliation.value).toBeNull();
  });

  it("零差异、零失败 → 不打扰用户", () => {
    const w = setup();
    w.totalRows.value = 340;
    w.sourceRowCount.value = 340;
    w.ignoredRowCount.value = 0;
    w.parseErrorCount.value = 0;
    expect(w.rowReconciliation.value).toBeNull();
  });

  it("出现未知操作名 → 差额、操作名与恒等式都能直接写出", () => {
    const w = setup();
    w.totalRows.value = 338;
    w.sourceRowCount.value = 340;
    w.ignoredRowCount.value = 1;
    w.parseErrorCount.value = 1;
    w.parseErrors.value = [
      {
        line: 42,
        field: "操作",
        message: "无法识别的操作类型「快速取现」",
        raw_value: "快速取现"
      }
    ];
    const r = w.rowReconciliation.value;
    expect(r).not.toBeNull();
    expect(r!.source).toBe(340);
    expect(r!.imported).toBe(338);
    expect(r!.ignored).toBe(1);
    expect(r!.failed).toBe(1);
    expect(r!.balanced).toBe(true);
    expect(r!.ops).toEqual(["快速取现"]);
  });

  it("恒等式不成立 → 标记对不平，不能假装一切正常", () => {
    const w = setup();
    w.totalRows.value = 300;
    w.sourceRowCount.value = 340;
    w.ignoredRowCount.value = 0;
    w.parseErrorCount.value = 0;
    expect(w.rowReconciliation.value).not.toBeNull();
    expect(w.rowReconciliation.value!.balanced).toBe(false);
  });

  it("多个未知操作名去重后只列一次", () => {
    const w = setup();
    w.totalRows.value = 338;
    w.sourceRowCount.value = 340;
    w.parseErrorCount.value = 2;
    w.parseErrors.value = [
      { line: 4, field: "操作", message: "…", raw_value: "快速取现" },
      { line: 9, field: "操作", message: "…", raw_value: "快速取现" }
    ];
    expect(w.rowReconciliation.value!.ops).toEqual(["快速取现"]);
  });

  it("换文件时清空对账状态，避免上一份文件的差额挂在新预览上", () => {
    const w = setup();
    w.sourceRowCount.value = 340;
    w.parseErrors.value = [
      { line: 4, field: null, message: "…", raw_value: "快速取现" }
    ];
    w.parseErrorCount.value = 1;
    w.ignoredRowCount.value = 1;
    w.clearImportState();
    expect(w.sourceRowCount.value).toBeNull();
    expect(w.parseErrors.value).toEqual([]);
    expect(w.parseErrorCount.value).toBe(0);
    expect(w.ignoredRowCount.value).toBe(0);
    expect(w.rowReconciliation.value).toBeNull();
  });

  it("已识别但不支持的行（新股申购）→ 必须把原因与补救方式写出来", () => {
    const w = setup();
    w.totalRows.value = 2;
    w.sourceRowCount.value = 4;
    w.parseErrorCount.value = 2;
    w.parseErrors.value = [
      {
        line: 2,
        field: "业务名称",
        message:
          "业务名「新股中签」属于新股申购中签，当前版本仅支持可转债打新，该行未纳入导入；请在导入后手动补录这笔建仓",
        raw_value: "新股中签"
      },
      {
        line: 3,
        field: "业务名称",
        message:
          "业务名「新股中签缴款」属于新股申购中签，当前版本仅支持可转债打新，该行未纳入导入；请在导入后手动补录这笔建仓",
        raw_value: "新股中签缴款"
      }
    ];
    const r = w.rowReconciliation.value!;
    expect(r.reasons).toHaveLength(2);
    expect(r.reasons[0]).toContain("仅支持可转债打新");
    // 新股不是「未登记的业务名」，不能给「去映射表登记」这种错误指引
    expect(r.hasUnknownOp).toBe(false);
  });

  it("未登记业务名的原因不与 ops 重复展示，且保留映射表指引", () => {
    const w = setup();
    w.totalRows.value = 338;
    w.sourceRowCount.value = 340;
    w.parseErrorCount.value = 1;
    w.parseErrors.value = [
      {
        line: 42,
        field: "业务名称",
        message: "无法识别的业务名称「快速取现」，该行未纳入导入",
        raw_value: "快速取现"
      }
    ];
    const r = w.rowReconciliation.value!;
    expect(r.ops).toEqual(["快速取现"]);
    expect(r.reasons).toEqual([]);
    expect(r.hasUnknownOp).toBe(true);
  });
});
