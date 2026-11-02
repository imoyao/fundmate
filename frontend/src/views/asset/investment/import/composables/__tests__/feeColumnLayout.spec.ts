import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";
import { clearFeeBreakdownOnEdit } from "../cellEditLogic";

/**
 * 手续费列回归（2026-11-02，决策「换列不加列」）。
 *
 * 背景：#1790 为守住「11 列 / 1060px 不横向滚动」把手手续费列退场，可见性交给
 * 金额列 tooltip。实测不够——tooltip 只能解释已有差额，**补录不了缺失值**，而
 * 手续费直接进买入成本与卖出已实现（pnl_service），漏记即静默少算。
 *
 * 本次契约：
 * 1. 手续费列回来，列数仍为 11（数据列 9 + 勾选 + 操作）——靠移除备注列
 *    （内容折进产品信息第二行）+ 配置目标 110→100 腾位，不是加列；
 * 2. 最小宽合计不超 1060px 预算（1200px 视口无横向滚动）；
 * 3. fee 与量价一样可就地编辑（后端 fee 取自预览行，手改真实生效）；
 * 4. 手改总额必须同步清空 #2137 四列拆分，否则
 *    `Transaction.before_insert` 的「拆分之和 == fee」会让整批导入抛 ValueError。
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

/** 勾选列固定 50 + 操作列固定 120（模板硬编码，不在 tableColumns 里） */
const FIXED_COL_WIDTH = 50 + 120;
/** #1790 / §6.1 的视口预算 */
const WIDTH_BUDGET = 1060;

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
    notes: "佣金含规费",
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

describe("手续费列：换列不加列", () => {
  it("股票模式数据列 9 个，手续费在列、备注退出", () => {
    const w = setup([feeRow()]);
    const props = w.tableColumns.value.map(c => c.prop);

    expect(w.tableColumns.value).toHaveLength(9);
    expect(props).toContain("fee");
    expect(props).not.toContain("notes");
    // 手续费紧跟金额列：用户「先看金额、再看被扣了多少费」
    expect(props.indexOf("fee")).toBe(props.indexOf("amount") + 1);
  });

  it("基金模式同样保留手续费列（申赎费），备注同样退出", () => {
    const w = setup([feeRow({ type: "fund" })]);
    w.selectedMode.value = "standard_fund";
    const props = w.tableColumns.value.map(c => c.prop);

    expect(w.tableColumns.value).toHaveLength(9);
    expect(props).toContain("fee");
    expect(props).not.toContain("notes");
  });

  it("最小宽合计不超 1060px 预算（1200 视口无横向滚动）", () => {
    const w = setup([feeRow()]);
    const sum = w.tableColumns.value.reduce(
      (acc, c) => acc + (c.minWidth ?? 0),
      0
    );

    expect(sum + FIXED_COL_WIDTH).toBeLessThanOrEqual(WIDTH_BUDGET);
  });

  it("配置目标让出宽度给手续费：110→106，手续费 70", () => {
    const w = setup([feeRow()]);
    const byProp = new Map(w.tableColumns.value.map(c => [c.prop, c]));

    expect(byProp.get("fee")?.minWidth).toBe(70);
    // 2026-11-02 实测量测后回补 6px：100px 时「长期增值」会被 ElSelect 截成「长期增…」，
    // 6px 从产品信息列（170→164）挪来，总宽仍是 1056（预算 1060）
    expect(byProp.get("allocation")?.minWidth).toBe(106);
  });

  it("备注内容仍在行数据里（列删了、信息没丢，产品信息第二行消费它）", () => {
    const w = setup([feeRow()]);
    expect(w.previewData.value[0].notes).toBe("佣金含规费");
  });
});

describe("手续费可编辑：手改总额真实生效", () => {
  it("startEdit(fee) 只点亮 fee 编辑态，其余编辑态互斥", () => {
    const w = setup([feeRow()]);
    const row = w.previewData.value[0];

    w.startEdit(row, "fee");

    expect(row.isEditingFee).toBe(true);
    expect(row.isEditingQty).toBe(false);
    expect(row.isEditingPrice).toBe(false);
    expect(row.isEditingAmount).toBe(false);
  });

  it("手改 fee 不触发金额重算（费用不是量价，动它会污染对账链）", () => {
    const w = setup([feeRow({ fee: null })]);
    const row = w.previewData.value[0];
    const beforeAmount = row.amount;
    const beforePrice = row.price;

    w.startEdit(row, "fee");
    row.fee = 7.5;
    w.finishEdit(row, "fee", true);

    expect(row.fee).toBe(7.5);
    expect(row.amount).toBe(beforeAmount);
    expect(row.price).toBe(beforePrice);
    expect(row.isEditingFee).toBe(false);
  });

  it("拆分四列齐全时手改总额：清空拆分并提示（否则 before_insert 让整批失败）", () => {
    const w = setup([
      feeRow({
        fee: 5.81,
        fee_commission: 5,
        fee_stamp_duty: 0,
        fee_transfer_fee: 0.81,
        fee_other: 0
      })
    ]);
    const row = w.previewData.value[0];

    w.startEdit(row, "fee");
    row.fee = 6.2;
    w.finishEdit(row, "fee", true);

    expect(row.fee).toBe(6.2);
    expect(row.fee_commission).toBeNull();
    expect(row.fee_stamp_duty).toBeNull();
    expect(row.fee_transfer_fee).toBeNull();
    expect(row.fee_other).toBeNull();
    expect(mocks.elMessage.warning).toHaveBeenCalled();
  });

  it("本来没有拆分（全空）时手改总额：不弹多余提示", () => {
    const w = setup([feeRow({ fee: null })]);
    const row = w.previewData.value[0];

    w.startEdit(row, "fee");
    row.fee = 3;
    w.finishEdit(row, "fee", true);

    expect(row.fee).toBe(3);
    expect(mocks.elMessage.warning).not.toHaveBeenCalled();
  });

  it("Esc 取消不吃掉拆分：只有 save=true 才清", () => {
    const w = setup([
      feeRow({
        fee: 5.81,
        fee_commission: 5,
        fee_stamp_duty: 0,
        fee_transfer_fee: 0.81,
        fee_other: 0
      })
    ]);
    const row = w.previewData.value[0];

    w.startEdit(row, "fee");
    row.fee = 99;
    w.cancelEdit(row, "fee");

    expect(row.fee).toBe(5.81);
    expect(row.fee_commission).toBe(5);
    expect(mocks.elMessage.warning).not.toHaveBeenCalled();
  });
});

describe("clearFeeBreakdownOnEdit 纯函数契约", () => {
  it("非 fee 字段一律不动", () => {
    const row: any = { fee_commission: 1, fee_stamp_duty: 0 };
    expect(clearFeeBreakdownOnEdit(row, "amount")).toBe(false);
    expect(row.fee_commission).toBe(1);
  });

  it("空串与 null 混合也一并归零（后端对 ''+数字混合会抛 ValueError）", () => {
    const row: any = { fee_commission: "", fee_stamp_duty: null };
    // 清理动作做了（避免 '' 残留与数字混合），但没有数字明细 → 不提示
    expect(clearFeeBreakdownOnEdit(row, "fee")).toBe(false);
    expect(row.fee_commission).toBeNull();
  });

  it("全空 / 缺键的行不做任何事", () => {
    const row: any = {};
    expect(clearFeeBreakdownOnEdit(row, "fee")).toBe(false);
    expect("fee_commission" in row).toBe(false);
  });
});
