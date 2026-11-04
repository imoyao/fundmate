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

/**
 * 底栏三个数字互相打架（#2840）。
 *
 * 现场：
 * ```
 * 已选择 169 条，另有 169 条暂不导入   [跳过这 169 条，导入 40 条]  [确认导入 169 条]
 * ```
 * 左边两个 169 相加是 338（全表），按钮上的 169+40 是 209（不含转账），主按钮
 * 又是 169（含转账）——三个分母，用户没法核对「银证转账到底在不在里面」。
 * 根因：`pendingFixCount` 刻意排除转账行（它数的是待修问题行），却被当成
 * 「未勾选」展示；而按钮执行的是「重置勾选为正常行」，会连已勾的转账一起清掉。
 */
describe("底栏计数的分母必须一致（#2840）", () => {
  const transfer = () =>
    row({
      symbol: "__CASH__",
      type: "cash",
      op_type: "deposit",
      is_cash_transfer: true,
      quantity: 0,
      price: 0
    });

  it("未勾选 = 全表 − 已选，两个数可以互算回总条数", () => {
    const w = setup([row(), row(), transfer()]);
    w.selectedKeys.value = new Set([w.previewData.value[0]._rowKey]);

    expect(w.selectedCount.value).toBe(1);
    expect(w.unselectedCount.value).toBe(2);
    expect(w.selectedCount.value + w.unselectedCount.value).toBe(
      w.previewData.value.length
    );
  });

  it("已选转账条数只数「勾上了的」转账行，用来解释勾选里含不含转账", () => {
    const w = setup([row(), transfer(), transfer()]);

    expect(w.selectedTransferCount.value).toBe(0);

    w.selectedKeys.value = new Set([w.previewData.value[1]._rowKey]);
    expect(w.selectedTransferCount.value).toBe(1);
  });

  it("全选时未勾选为 0，且已选转账条数覆盖全部转账行", () => {
    const w = setup([row(), transfer()]);
    w.selectAllValid();
    // 转账行不在 selectAllValid 作用域内（要用户显式决定），这里手动补上
    w.selectedKeys.value.add(w.previewData.value[1]._rowKey);

    expect(w.unselectedCount.value).toBe(0);
    expect(w.selectedTransferCount.value).toBe(1);
  });
});

/**
 * 现金类收益（利息归本）被当成银证转账（#2840）。
 *
 * 后端曾用 `asset_type == 'cash'` 推 `is_cash_transfer`，于是「利息归本」
 * （asset_type=cash、business_type=dividend_cash）在前端：默认不勾、须先关联
 * 现金账户、计入「含 N 条银证转账」，还挂着「代码未匹配」——三处都解释不通。
 * 语义上它是投资收益，不是银行↔证券搬钱。
 */
describe("现金类收益不按转账/缺代码处理（#2840）", () => {
  const interest = () =>
    row({
      symbol: "",
      name: "利息归本",
      type: "cash",
      op_type: "dividend_cash",
      quantity: 0,
      price: 0,
      amount: 0.9
    });

  it("type=cash 且无代码 → 不判代码未匹配，默认可导入", () => {
    const w = setup([interest()]);
    const r = w.previewData.value[0];

    expect(w.isMissingCode(r)).toBe(false);
    expect(w.isAutoSelectableRow(r)).toBe(true);
    expect(w.isRowSelectable(r)).toBe(true);
    expect(w.pendingFixCount.value).toBe(0);
  });

  it("股票行缺代码仍判代码未匹配——现金豁免不外溢到有标的的行", () => {
    const w = setup([row({ symbol: "", type: "stock" })]);

    expect(w.isMissingCode(w.previewData.value[0])).toBe(true);
    expect(w.isAutoSelectableRow(w.previewData.value[0])).toBe(false);
  });

  it("全选有效行会把利息归本带上，导入条数如实计数", () => {
    const w = setup([row(), interest()]);

    w.selectAllValid();

    expect(w.selectedCount.value).toBe(2);
    expect(w.selectedTransferCount.value).toBe(0);
  });
});

/**
 * 表头「全选」的三态判据必须与 selectAllValid 同源（#2840）。
 *
 * 这里曾手抄一份同样的条件，注释还写着「eligible 口径与 selectAllValid 一致」，
 * 实际漏了 isMissingCode：只要表里有一条缺代码行，selectedKeys 就永远追不上
 * eligible，全选后表头还挂在半选态——用户会以为「没选全」，再点一次反而清空。
 */
describe("表头全选三态与可勾选谓词同源", () => {
  it("含缺代码行时，重算三态仍落到「全选」（不挂在半选）", () => {
    const w = setup([row(), row({ symbol: "" })]);
    w.selectAllValid();
    // selectAllValid 直接置位，不走重算——真正会暴露漂移的是任何一次
    // 逐行勾选触发的 updateSelectAllState。
    w.handleRowCheckboxChange(w.previewData.value[0], true);

    expect(w.selectedCount.value).toBe(1);
    expect(w.isAllSelected.value).toBe(true);
    expect(w.isIndeterminate.value).toBe(false);
  });

  it("含转账行时同理（转账不在自动勾选范围，但不能挡住全选态）", () => {
    const w = setup([
      row(),
      row({
        symbol: "__CASH__",
        type: "cash",
        op_type: "deposit",
        is_cash_transfer: true,
        quantity: 0,
        price: 0
      })
    ]);

    w.selectAllValid();
    w.handleRowCheckboxChange(w.previewData.value[0], true);

    expect(w.isAllSelected.value).toBe(true);
    expect(w.isIndeterminate.value).toBe(false);
  });
});

/**
 * 基金红利拨入的资产口径（#2843）。
 *
 * 同花顺对「基金红利拨入」不给代码也不给名称（table1101.xls 里 5 条，两列皆空），
 * 后端以前兜底成 `stock`：预览页显示「股票」、因 symbol 为空挂「代码未匹配」而
 * 勾不上——既导不进，又会被算进投资收益。经 owner 确认（2026-11-03）它是
 * 银河水星现金添利（970164）的月度收益结转，后端改判 `money_fund`。
 * 前端必须同步放行：否则后端改对了，界面还是勾不动。
 */
describe("基金红利按货基口径处理（#2843）", () => {
  const fundDividend = () =>
    row({
      symbol: "",
      name: "",
      type: "money_fund",
      display_type: "货币基金",
      op_type: "dividend_cash",
      quantity: 0,
      price: 0,
      amount: 2.1,
      fee: 0
    });

  it("type=money_fund 且无代码 → 不判代码未匹配，默认可导入", () => {
    const w = setup([fundDividend()]);
    const r = w.previewData.value[0];

    expect(w.isMissingCode(r)).toBe(false);
    expect(w.isAutoSelectableRow(r)).toBe(true);
    expect(w.isRowSelectable(r)).toBe(true);
    expect(w.pendingFixCount.value).toBe(0);
  });

  it("它不计入「含 N 条银证转账」", () => {
    const w = setup([fundDividend()]);

    w.selectAllValid();

    expect(w.selectedCount.value).toBe(1);
    expect(w.selectedTransferCount.value).toBe(0);
  });

  it("普通基金（fund）缺代码仍判代码未匹配——货基豁免不外溢", () => {
    const w = setup([row({ symbol: "", type: "fund" })]);

    expect(w.isMissingCode(w.previewData.value[0])).toBe(true);
    expect(w.isAutoSelectableRow(w.previewData.value[0])).toBe(false);
  });
});
