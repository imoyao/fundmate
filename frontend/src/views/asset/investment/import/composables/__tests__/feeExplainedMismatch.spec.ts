import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";

/**
 * 金额差额「被手续费解释」的回归测试（2026-11-02）。
 *
 * 背景（真实数据，库内 transactions id=3079 海大集团卖出）：
 *   数量 200 × 单价 47.97 = 9,594.00（入库成交额）
 *   交割单发生金额       = 9,588.19（含手续费 5.81）
 * 同花顺解析的 `amount` 取**含费发生额**，而入库 amount 恒按 单价×数量 重算、fee 另列。
 * 旧判据 `|差额| > 0.01` 于是把每一笔带费行都打成「金额与数量×价格不符」——
 * 用户看到的一屏 152 条「需要修正」，绝大多数是这一条造成的假警报。
 *
 * 被测契约：
 * 1. 差额 ≤ |fee| + 0.01 → 被手续费解释，**不算 mismatch**，归「数据完整」可导入；
 * 2. 差额 > |fee| + 0.01 → 真对不上，仍进 mismatch 分区（费用列可能漏项）；
 * 3. 两者互斥，且无 fee 字段（旧草稿/旧解析结果）时回落旧口径，不静默放行；
 * 4. #1791 的和式不变量与「卡片条数 = 分区行数」不被破坏。
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

/**
 * 带手续费的真实形态：发生金额 = 成交额 − 手续费。
 * 数值取自 transactions id=3079（200 股 @47.97，fee 5.81），不是手编的整数。
 */
function feeRow(overrides: Record<string, unknown> = {}) {
  return {
    symbol: "002311",
    name: "海大集团",
    op_type: "sell",
    trade_date: "2026-10-28",
    quantity: 200,
    price: 47.97,
    amount: 9588.19,
    fee: 5.81,
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

describe("费用容差：差额被手续费解释时不再判错", () => {
  it("id 3079 真实带费行：差额 5.81 == fee，不算 mismatch 且归「数据完整」", () => {
    const w = setup([feeRow()]);
    const row = w.previewData.value[0];

    expect(w.feeDiffOf(row)).toBeCloseTo(5.81, 2);
    expect(w.isFeeExplained(row)).toBe(true);
    expect(w.isAmountMismatch(row)).toBe(false);

    // 核心回归：修复前这里会被打成 fix，用户被迫点「修正金额」
    expect(w.categorizeRow(row)).toBe("complete");
    expect(w.fixSectionRows.value.mismatch).toHaveLength(0);
  });

  it("差额大于手续费：仍进 mismatch 分区（费用列可能漏项）", () => {
    const w = setup([feeRow({ amount: 9580 })]);
    const row = w.previewData.value[0];

    expect(w.feeDiffOf(row)).toBeCloseTo(14, 2);
    expect(w.isFeeExplained(row)).toBe(false);
    expect(w.isAmountMismatch(row)).toBe(true);
    expect(w.fixSectionRows.value.mismatch).toHaveLength(1);
  });

  it("无 fee 字段（旧草稿 / 旧解析结果）回落旧口径，不静默放行", () => {
    const w = setup([feeRow({ fee: undefined })]);
    const row = w.previewData.value[0];

    expect(w.isFeeExplained(row)).toBe(false);
    expect(w.isAmountMismatch(row)).toBe(true);
  });

  it("恰好等于 fee+0.01 视为已解释；再多 0.01 即判错（边界）", () => {
    const w = setup([
      // 100 × 10 = 1000，amount 980 → 差额 20，fee 20
      feeRow({ quantity: 100, price: 10, amount: 980, fee: 20 }),
      // amount 979 → 差额 21，fee 20 → 超出可解释范围
      feeRow({ quantity: 100, price: 10, amount: 979, fee: 20 })
    ]);
    const [inRange, overRange] = w.previewData.value;

    expect(w.isFeeExplained(inRange)).toBe(true);
    expect(w.isAmountMismatch(inRange)).toBe(false);
    expect(w.isFeeExplained(overRange)).toBe(false);
    expect(w.isAmountMismatch(overRange)).toBe(true);
  });

  it("两个谓词互斥：差额为正时不可能同时成立", () => {
    const w = setup([
      feeRow(),
      feeRow({ amount: 9580 }),
      feeRow({ amount: 9594 }), // 完全相等，两者皆 false
      feeRow({ fee: 0 })
    ]);

    w.previewData.value.forEach(row => {
      expect(w.isFeeExplained(row) && w.isAmountMismatch(row)).toBe(false);
    });

    // 完全相等的行两个谓词都不触发
    const exact = w.previewData.value[2];
    expect(w.isFeeExplained(exact)).toBe(false);
    expect(w.isAmountMismatch(exact)).toBe(false);
  });
});

describe("改动不破坏 #1791 的合计不变量", () => {
  it("三卡片条数之和恒等于总行数（带费行归 complete 后仍成立）", () => {
    const w = setup([
      feeRow(),
      feeRow({ amount: 9580 }),
      feeRow({ is_duplicate: true }),
      feeRow({ error: "解析失败" })
    ]);

    const counts = w.summaryCounts.value;
    expect(counts.complete + counts.duplicate + counts.fix).toBe(
      w.previewData.value.length
    );
  });

  it("「需要修正」条数 = 四分区行数之和（mismatch 收紧后仍对齐）", () => {
    const w = setup([
      feeRow(),
      feeRow({ amount: 9580 }),
      feeRow({ error: "解析失败" }),
      feeRow({ symbol: "" })
    ]);

    const sections = w.fixSectionRows.value;
    const sum =
      sections.error.length +
      sections.missingCode.length +
      sections.missingQtyPrice.length +
      sections.mismatch.length;

    expect(w.summaryCounts.value.fix).toBe(sum);
  });

  it("带费行计入「可导入」而非「需要修正」：卡内条数直接下降", () => {
    const w = setup([feeRow(), feeRow({ amount: 9588.19 })]);
    expect(w.summaryCounts.value.fix).toBe(0);
    expect(w.summaryCounts.value.complete).toBe(2);
  });
});
