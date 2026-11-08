import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";

/**
 * #2901 上传兼容性提醒的取消路径。
 *
 * 旧实现把「返回重选」的 return 写在 ElMessageBox.confirm().catch 回调里，
 * 只退出回调、退不出 handleUpload——用户取消后仍会 await persistDraft() 落草稿、
 * 调 options.onSuccess 向上报成功。本 spec 钉住四条：
 * 1. 取消 = 放弃本次导入（不落草稿、不报成功、清空预览、totalRows 归零）；
 * 2. 继续 = 正常进第二步并落一次草稿；
 * 3. 无提醒 = 不弹框直接进第二步；
 * 4. 取消后 hasUnsavedDraftWork 判假 → 30s 自动保存不会写回被放弃的草稿。
 */

const mocks = vi.hoisted(() => ({
  saveDraft: vi.fn(),
  getDraftWithSet: vi.fn(),
  discardDraft: vi.fn(),
  parseFile: vi.fn(),
  confirm: vi.fn(),
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
  ElMessageBox: { confirm: mocks.confirm }
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
  parseFile: mocks.parseFile,
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

const RES = {
  data: [
    {
      op_type: "buy",
      code: "600000",
      name: "测试",
      quantity: 100,
      price: 10,
      amount: 1000
    }
  ],
  duplicate_count: 0,
  error_count: 0,
  source_row_count: 1,
  parse_errors: [],
  parse_error_count: 0,
  ignored_row_count: 0,
  compatibility_warning: "旧版格式，列顺序可能不一致"
};

function setup() {
  const w = useImportWizard();
  w.selectedLedgerId.value = 1;
  // 真实前置态：用户选账户经 onAccountSelected 把 currentStep 置 1，再上传
  w.currentStep.value = 1;
  w.ledgers.value = [
    {
      id: 1,
      name: "测试账户",
      default_allocation: "longterm"
    } as unknown as ReturnType<
      typeof useImportWizard
    >["ledgers"]["value"][number]
  ];
  return w;
}

type HandleUploadOpts = Parameters<
  ReturnType<typeof useImportWizard>["handleUpload"]
>[0];

function uploadOpts() {
  return {
    file: new File(["a,b"], "a.csv", { type: "text/csv" }),
    onSuccess: vi.fn(),
    onError: vi.fn()
  } as unknown as HandleUploadOpts;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.saveDraft.mockResolvedValue(undefined);
  mocks.parseFile.mockResolvedValue(RES);
});

describe("#2901 上传兼容性提醒的取消路径", () => {
  it("点「返回重选」：不落草稿、不报成功、不留预览数据", async () => {
    const w = setup();
    mocks.confirm.mockRejectedValue("cancel");
    const opts = uploadOpts();

    await w.handleUpload(opts);

    expect(opts.onSuccess).not.toHaveBeenCalled();
    expect(opts.onError).toHaveBeenCalledTimes(1);
    expect(mocks.saveDraft).not.toHaveBeenCalled();
    expect(w.previewData.value).toHaveLength(0);
    // totalRows=0 是取消分支显式归零的结果（它不在 clearImportState 的重置清单里）
    expect(w.totalRows.value).toBe(0);
    expect(w.currentStep.value).toBe(1);
    expect(w.uploadError.value).toBe("");
    expect(w.parsing.value).toBe(false);
  });

  it("点「继续导入」：进第二步、落一次草稿、报成功", async () => {
    const w = setup();
    mocks.confirm.mockResolvedValue("confirm");
    const opts = uploadOpts();

    await w.handleUpload(opts);

    expect(opts.onSuccess).toHaveBeenCalledTimes(1);
    expect(mocks.saveDraft).toHaveBeenCalledTimes(1);
    expect(w.currentStep.value).toBe(2);
    expect(w.previewData.value).toHaveLength(1);
  });

  it("无兼容性提醒：不弹框，直接进第二步", async () => {
    const w = setup();
    mocks.parseFile.mockResolvedValue({
      ...RES,
      compatibility_warning: ""
    });
    const opts = uploadOpts();

    await w.handleUpload(opts);

    expect(mocks.confirm).not.toHaveBeenCalled();
    expect(opts.onSuccess).toHaveBeenCalledTimes(1);
    expect(w.currentStep.value).toBe(2);
  });

  it("取消后 hasUnsavedDraftWork 判假：30s 自动保存不会把草稿写回去", async () => {
    const w = setup();
    mocks.confirm.mockRejectedValue("cancel");
    const opts = uploadOpts();

    await w.handleUpload(opts);

    expect(w.hasUnsavedDraftWork.value).toBe(false);
  });
});
