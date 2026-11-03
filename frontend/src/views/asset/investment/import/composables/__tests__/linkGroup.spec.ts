import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";

/**
 * 配对组（兑息 + 代扣税 / 兑付 + 股份转出）在预览页的行为契约（#2836）。
 *
 * 这批用例的由来是**真实数据实测**，不是推演：同花顺交割单里丰山转债的
 * 「债券兑息 90 + 债券兑息兑付 −18」两行，交割数量单价都填 60 / 1.5，于是
 * |60 × 1.5 − (−18)| = 108 元被判成「金额不一致」——一分钱问题都没有的数据
 * 被染成需要修正，而用户实际想问的是「为什么把这两笔当两件事」。
 *
 * 三条判据（对应下面前三个 describe）：
 * 1. 税额、兑付额与「数量 × 价格」无关，不能拿成交口径比对；
 * 2. 合并行用**组等式**（数量 × 单价 − 组内税额 = 净额），不是单行等式；
 * 3. 概览条的数字必须等于表格行数（合并后），否则用户数不出来。
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

/** 债券兑息行（丰山转债真实值：60 张、单价 1.5、利息 90 元） */
function interestRow(overrides: Record<string, unknown> = {}) {
  return {
    symbol: "SH113649",
    name: "丰山转债",
    op_type: "dividend_cash",
    trade_date: "2026-06-26",
    quantity: 60,
    price: 1.5,
    amount: 90,
    fee: 0,
    type: "bond",
    link_group_id: "bond_interest_tax:SH113649:2026-06-26",
    notes: "债券兑息",
    ...overrides
  };
}

/** 代扣个税行：沿用了利息行的数量单价，金额 −18 */
function taxRow(overrides: Record<string, unknown> = {}) {
  return {
    symbol: "SH113649",
    name: "丰山转债",
    op_type: "tax",
    trade_date: "2026-06-26",
    quantity: 60,
    price: 1.5,
    amount: -18,
    fee: 0,
    type: "bond",
    link_group_id: "bond_interest_tax:SH113649:2026-06-26",
    notes: "债券兑息兑付",
    ...overrides
  };
}

/** 债券兑付行：有到账额、常无成交均价 */
function redeemRow(overrides: Record<string, unknown> = {}) {
  return {
    symbol: "SZ128119",
    name: "龙大转债",
    op_type: "bond_redeem",
    trade_date: "2026-07-16",
    quantity: 0,
    price: 0,
    amount: 12430,
    fee: 0,
    type: "bond",
    notes: "债券兑付",
    ...overrides
  };
}

/** 兑付附带的股份转出：有份额、无现金、无价格 */
function shareOutRow(overrides: Record<string, unknown> = {}) {
  return {
    symbol: "SZ128119",
    name: "龙大转债",
    op_type: "withdraw",
    trade_date: "2026-07-16",
    quantity: 110,
    price: 0,
    amount: 0,
    fee: 0,
    type: "bond",
    notes: "股份转出",
    consumed_by: "redeem_share_clearing",
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

describe("税额与兑付额不参与「金额 = 数量 × 价格」判据", () => {
  it("代扣个税行不再被判「金额不一致」（旧实现差 108 元必红）", () => {
    const w = setup([taxRow()]);

    expect(w.isAmountMismatch(w.previewData.value[0]!)).toBe(false);
    expect(w.summaryCounts.value.fix).toBe(0);
  });

  it("兑付行没有成交均价也不算「待补全」（#2835 后这是常态）", () => {
    const w = setup([redeemRow()]);

    expect(w.isRowBlocked(w.previewData.value[0]!)).toBe(false);
    expect(w.summaryCounts.value.fix).toBe(0);
  });

  it("普通买卖行仍然按成交口径判差额（豁免没有放得太宽）", () => {
    const w = setup([
      {
        symbol: "002311",
        name: "海大集团",
        op_type: "sell",
        trade_date: "2026-10-28",
        quantity: 200,
        price: 47.97,
        amount: 9000, // 应为 9594，差 594 且无手续费可解释
        fee: 0,
        type: "stock"
      }
    ]);

    expect(w.isAmountMismatch(w.previewData.value[0]!)).toBe(true);
    expect(w.summaryCounts.value.fix).toBe(1);
  });
});

describe("合并行用组等式：数量 × 单价 − 组内税额 = 净额", () => {
  it("兑息 + 代扣税折成一行，净额 72 且判为可导入", () => {
    const w = setup([interestRow(), taxRow()]);

    const rows = w.filteredPagedData.value;
    expect(rows).toHaveLength(1);
    const merged = rows[0]!;
    expect(merged.is_merged).toBe(true);
    expect(merged.amount).toBe(72); // 90 − 18
    expect(merged.notes).toContain("税前90.00元");
    expect(merged.notes).toContain("实收72.00元");

    expect(w.isAmountMismatch(merged)).toBe(false);
    expect(w.categorizeRow(merged)).toBe("complete");
  });

  it("利息行自身金额对不上时不合并，差额照报（组等式不是和稀泥）", () => {
    // 利息行写成 60 元而 60 × 1.5 = 90：这 30 元没有任何东西能解释 → 该组有问题
    //
    // 注：组等式化简后恰好等于「利息行自身的 数量×单价 == 金额」（税额在净额与
    // 扣除项里各出现一次、正负抵消），所以组级自洽是**由利息行决定**的——
    // 这也解释了为什么这里要动利息行而不是动税额。
    const w = setup([interestRow({ amount: 60 }), taxRow()]);

    expect(w.filteredPagedData.value).toHaveLength(2);
    expect(w.summaryCounts.value.fix).toBeGreaterThan(0);
  });

  it("组内任一行有问题就不合并，两行各自展示（否则用户改不到真数据）", () => {
    const w = setup([interestRow({ error: "交易日期无法解析" }), taxRow()]);

    const rows = w.filteredPagedData.value;
    expect(rows).toHaveLength(2);
    expect(rows.every(r => !r.is_merged)).toBe(true);
  });

  it("跨日的同类两行不会被合并（组名不同）", () => {
    const w = setup([
      interestRow(),
      taxRow({
        trade_date: "2026-06-27",
        link_group_id: "bond_interest_tax:SH113649:2026-06-27"
      })
    ]);

    const rows = w.filteredPagedData.value;
    expect(rows).toHaveLength(2);
    expect(rows.some(r => r.is_merged)).toBe(false);
  });
});

describe("概览条数字 = 表格行数（合并后）", () => {
  it("一组息+税：概览条 1 条，表格 1 行（旧实现是 2 条对 1 行）", () => {
    const w = setup([interestRow(), taxRow()]);

    const counts = w.summaryCounts.value;
    expect(counts.complete).toBe(1);
    expect(counts.fix).toBe(0);
    expect(counts.complete + counts.duplicate + counts.fix).toBe(
      w.filteredPagedData.value.length
    );
  });

  it("「需要修正」条数仍等于四分区之和（共谓词没被合并逻辑破坏）", () => {
    const w = setup([
      interestRow(),
      taxRow(),
      // 一条真问题行（代码未匹配）
      { ...interestRow(), symbol: "", name: "无主债券", link_group_id: null }
    ]);

    const b = w.fixBreakdown.value;
    expect(b.error + b.missingCode + b.missingQtyPrice + b.mismatch).toBe(
      w.summaryCounts.value.fix
    );
  });
});

describe("被配对消费的行（股份转出）", () => {
  it("不判待补全、不计入需要修正", () => {
    const w = setup([redeemRow(), shareOutRow()]);

    expect(w.isRowBlocked(w.previewData.value[1]!)).toBe(false);
    expect(w.summaryCounts.value.fix).toBe(0);
  });

  it("默认不勾选，也不可手动勾选（勾了后端也会跳过）", () => {
    const w = setup([redeemRow(), shareOutRow()]);

    w.selectAllValid();
    const consumed = w.previewData.value[1]!;
    expect(w.isRowSelected(consumed)).toBe(false);
    expect(w.isRowSelectable(consumed)).toBe(false);

    // 兑付行本身照常可选
    expect(w.isRowSelected(w.previewData.value[0]!)).toBe(true);
  });
});
