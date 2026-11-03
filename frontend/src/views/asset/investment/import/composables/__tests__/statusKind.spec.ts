import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";
import { statusKindOf } from "../statusKind";

/**
 * 状态标签判据（#2836）。
 *
 * 这组用例守的是一次真实事故：`StatusCell.vue` 的 `v-else-if` 链里没有
 * 「金额对不上」这一档，于是这类行一路落到末尾的 `v-else`，拿到绿色「正常」。
 * 而同一行在概览条里被算进「需要修正」、在修正面板里躺在「金额对不上」分区、
 * 还默认可勾选直接入库——错账被标绿，用户没有任何线索去怀疑它。
 *
 * 模板的 `v-else` 会**静默**吞掉任何漏写的判据，组件内部无法自证完整；把判据
 * 抽成 `statusKindOf` 后，下面第一条不变式才能被真正钉住。
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

function row(overrides: Record<string, unknown> = {}) {
  return {
    symbol: "002311",
    name: "海大集团",
    op_type: "buy",
    trade_date: "2026-10-28",
    quantity: 100,
    price: 10,
    amount: 1000,
    fee: 5,
    type: "stock",
    ...overrides
  };
}

function setup(rows: Array<Record<string, unknown>>) {
  const w = useImportWizard();
  w.previewData.value = w.addRowKeys(rows);
  return w;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.saveDraft.mockResolvedValue(undefined);
  mocks.getDraftWithSet.mockResolvedValue(null);
  mocks.discardDraft.mockResolvedValue(undefined);
  mocks.getLedgers.mockResolvedValue([]);
});

describe("金额对不上不再被标成「正常」", () => {
  it("差额超出全部手续费 → mismatch（而不是 ok）", () => {
    const w = setup([row({ amount: 1200, fee: 5 })]);
    const r = w.previewData.value[0];

    expect(
      statusKindOf(r, {
        isRowBlocked: w.isRowBlocked,
        isFeeExplained: w.isFeeExplained,
        isAmountMismatch: w.isAmountMismatch,
        isMissingCode: w.isMissingCode
      })
    ).toBe("mismatch");
  });

  it("差额刚好等于手续费 → feeExplained（仍可导入、仍不是「正常」）", () => {
    const w = setup([row({ amount: 1005, fee: 5 })]);
    const r = w.previewData.value[0];

    expect(
      statusKindOf(r, {
        isRowBlocked: w.isRowBlocked,
        isFeeExplained: w.isFeeExplained,
        isAmountMismatch: w.isAmountMismatch,
        isMissingCode: w.isMissingCode
      })
    ).toBe("feeExplained");
  });

  it("完全对得上 → ok", () => {
    const w = setup([row()]);
    const r = w.previewData.value[0];

    expect(
      statusKindOf(r, {
        isRowBlocked: w.isRowBlocked,
        isFeeExplained: w.isFeeExplained,
        isAmountMismatch: w.isAmountMismatch,
        isMissingCode: w.isMissingCode
      })
    ).toBe("ok");
  });

  /**
   * 结构性不变式：概览条的 fix 分类与状态标签必须同源。
   *
   * 只要 `categorizeRow` 说「这行要修」，状态列就不许给绿色「正常」——
   * 将来有人往 categorizeRow 里加一档 fix 判定、却忘了配套状态标签，
   * 这条会立刻转红，而不是让用户对着一枚绿标签导入错账。
   */
  it("不变式：凡 categorizeRow 判为 fix 的行，状态不得为 ok", () => {
    const w = setup([
      row({ amount: 1200, fee: 5 }), // 金额对不上
      row({ price: null }), // 缺单价
      row({ symbol: "" }), // 代码未匹配
      row({ error: "解析失败" }), // 解析错误
      row() // 干净行（对照组）
    ]);
    const p = {
      isRowBlocked: w.isRowBlocked,
      isFeeExplained: w.isFeeExplained,
      isAmountMismatch: w.isAmountMismatch,
      isMissingCode: w.isMissingCode
    };

    const violated = w.previewData.value.filter(
      r => w.categorizeRow(r) === "fix" && statusKindOf(r, p) === "ok"
    );

    expect(violated.map(r => r.error ?? r.symbol)).toEqual([]);
    // 对照组必须真的是 ok，否则上面那条可能靠「全都不是 ok」蒙混通过
    expect(statusKindOf(w.previewData.value[4], p)).toBe("ok");
  });
});

describe("优先级：先命中的先说", () => {
  it("被配对消费优先于一切（它是「不用管」不是「有问题」）", () => {
    const w = setup([
      row({ amount: 1200, fee: 5, error: "忽略我", consumed_by: "bond_redeem" })
    ]);
    expect(
      statusKindOf(w.previewData.value[0], {
        isRowBlocked: w.isRowBlocked,
        isFeeExplained: w.isFeeExplained,
        isAmountMismatch: w.isAmountMismatch,
        isMissingCode: w.isMissingCode
      })
    ).toBe("consumed");
  });

  it("缺字段优先于金额对不上（先补齐才谈得上核对）", () => {
    const w = setup([row({ price: null, amount: 1200, fee: 5 })]);
    expect(
      statusKindOf(w.previewData.value[0], {
        isRowBlocked: w.isRowBlocked,
        isFeeExplained: w.isFeeExplained,
        isAmountMismatch: w.isAmountMismatch,
        isMissingCode: w.isMissingCode
      })
    ).toBe("blocked");
  });

  it("重复优先于金额对不上（跳过的行不必再纠金额）", () => {
    const w = setup([row({ amount: 1200, fee: 5, is_duplicate: true })]);
    expect(
      statusKindOf(w.previewData.value[0], {
        isRowBlocked: w.isRowBlocked,
        isFeeExplained: w.isFeeExplained,
        isAmountMismatch: w.isAmountMismatch,
        isMissingCode: w.isMissingCode
      })
    ).toBe("duplicate");
  });

  it("推算行（is_calculated）给「待确认」而不是「正常」", () => {
    const w = setup([row({ is_calculated: true })]);
    expect(
      statusKindOf(w.previewData.value[0], {
        isRowBlocked: w.isRowBlocked,
        isFeeExplained: w.isFeeExplained,
        isAmountMismatch: w.isAmountMismatch,
        isMissingCode: w.isMissingCode
      })
    ).toBe("calculated");
  });

  it("配对税额存疑（link_warning）单独一档，不并进金额口径", () => {
    const w = setup([row({ link_warning: "税率不符" })]);
    expect(
      statusKindOf(w.previewData.value[0], {
        isRowBlocked: w.isRowBlocked,
        isFeeExplained: w.isFeeExplained,
        isAmountMismatch: w.isAmountMismatch,
        isMissingCode: w.isMissingCode
      })
    ).toBe("linkWarning");
  });
});
