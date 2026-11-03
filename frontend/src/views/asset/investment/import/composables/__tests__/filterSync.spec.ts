import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";

/**
 * 筛选 / 计数 / 可勾选三处判据同源（#2836）。
 *
 * 真实报障现场（338 行交割单，1440 视口）：
 *
 * ```
 * 概览条：● 直接可导入 169   ● 疑似重复 168   ● 需要修正 1（= 代码未匹配 1）
 * 筛选栏：只看问题数据 [开]
 * 表格：  暂无数据
 * 底栏：  已选择 40 条，另有 168 条暂不导入
 * ```
 *
 * 那 1 条代码未匹配的行**三处都没算它**：问题视图的过滤谓词里没有
 * `isMissingCode`、底栏的加法里也没有。用户对着一句「需要修正 1」找不到那 1 条。
 *
 * 根因是同一件事写了三份判据：`isRowBlocked`（缺数量/价格）、问题视图的手写
 * or 链、底栏的 duplicate+blocked+error 加法。本文件把三者钉到 `categorizeRow`
 * 与 `isRowSelectable` 上，任何一处再长出私有判据都会在这里转红。
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

describe("「只看问题数据」与概览条三卡同源", () => {
  it("代码未匹配的行在问题视图里可见（原先被过滤成「暂无数据」）", () => {
    const w = setup([row({ symbol: "" }), row()]);

    w.showProblemOnly.value = true;

    expect(w.filteredPagedData.value).toHaveLength(1);
    expect(w.filteredPagedData.value[0].symbol).toBe("");
  });

  it("金额对不上的行同样可见（原先也被漏在 or 链之外）", () => {
    const w = setup([row({ amount: 1200, fee: 5 }), row()]);

    w.showProblemOnly.value = true;

    expect(w.filteredPagedData.value).toHaveLength(1);
    expect(w.filteredPagedData.value[0].amount).toBe(1200);
  });

  it("干净行在问题视图里不出现", () => {
    const w = setup([row()]);

    w.showProblemOnly.value = true;

    expect(w.filteredPagedData.value).toHaveLength(0);
  });

  /**
   * 这条是「概览条说得出口、表格就得看得见」的结构性版本：
   * 概览条上每一个非零类的行，切到问题视图后都必须逐条出现。
   */
  it("不变式：概览条非零类之和 == 问题视图行数", () => {
    const w = setup([
      row(), // 干净
      row({ symbol: "" }), // 代码未匹配
      row({ amount: 1200, fee: 5 }), // 金额不符
      row({ price: null }), // 缺单价
      row({ is_duplicate: true }) // 重复
    ]);

    w.showProblemOnly.value = true;

    const cards = w.summaryCounts.value.fix + w.summaryCounts.value.duplicate;
    expect(w.filteredPagedData.value).toHaveLength(cards);
  });
});

describe("「暂不导入」与可勾选同源", () => {
  it("代码未匹配的行不可勾（默认不选 + 手动也点不了）", () => {
    const w = setup([row({ symbol: "" })]);
    const r = w.previewData.value[0];

    expect(w.isRowSelectable(r)).toBe(false);
    expect(w.isAutoSelectableRow(r)).toBe(false);
  });

  it("pendingFixCount == 不可勾行数（转账行与干净行都不计）", () => {
    const w = setup([
      row(), // 干净 → 可勾，不计
      row({ symbol: "" }), // 代码未匹配 → 计 1
      row({ is_duplicate: true }), // 重复 → 计 1
      row({
        // 转账行 → 不计（勾不勾取决于是否关联现金账户，不是待修问题）
        symbol: "__CASH__",
        type: "cash",
        op_type: "deposit",
        is_cash_transfer: true,
        quantity: 0,
        price: 0
      })
    ]);

    expect(w.pendingFixCount.value).toBe(2);
  });

  /**
   * 底栏按钮「跳过这 N 条，导入 M 条」的实际动作是
   * `clearAllSelection + selectAllValid`。这条钉住「N + M + 转账行 == 全部」，
   * 保证两个数字加起来能对上用户手里的总行数。
   */
  it("跳过 N 条 + 导入 M 条 + 转账行 == 全部行数", () => {
    const w = setup([
      row(),
      row({ symbol: "" }),
      row({ is_duplicate: true }),
      row({ is_cash_transfer: true, symbol: "__CASH__", type: "cash" })
    ]);
    const total = w.previewData.value.length;
    const transfers = w.previewData.value.filter(
      r => r.is_cash_transfer
    ).length;

    w.selectAllValid();

    expect(w.pendingFixCount.value + w.selectedCount.value + transfers).toBe(
      total
    );
  });

  it("转账行即使当前勾不上，也不算「暂不导入」", () => {
    const w = setup([row({ is_cash_transfer: true, symbol: "__CASH__" })]);

    // 未关联现金账户 → 不可勾
    expect(w.isRowSelectable(w.previewData.value[0])).toBe(false);
    // 但它的开关是「关联哪个账户」，不是「这行有问题」——不该混进待修数字
    expect(w.pendingFixCount.value).toBe(0);
  });

  /**
   * 补代码的动作本身就是在说「这些行要导入」。
   *
   * 代码未匹配的行原先既不可勾、也不默认选；如果补完代码还要用户再勾一次，
   * 就会出现「修好了却导不进去」的第二次踩坑。
   */
  it("补上代码后该行自动入选", async () => {
    const w = setup([row({ symbol: "" })]);
    const r = w.previewData.value[0];
    expect(w.isRowSelected(r)).toBe(false);

    await w.batchFillCode([r], "600000");

    expect(r.symbol).toBe("600000");
    expect(w.isRowSelected(r)).toBe(true);
  });
});
