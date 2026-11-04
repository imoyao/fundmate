import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImportWizard } from "../useImportWizard";

/**
 * 概览条（三卡片 → 一行胶囊，2026-11-02）的行为契约。
 *
 * 这轮改动动了三处**语义**，不是只换皮，故各留一条判据：
 * 1. 分区条数 tag 的颜色按「问题性质」定档，不再按条数分档——
 *    旧实现 `>200 danger / >50 warning / >10 info / 其余 success` 会把
 *    「代码未匹配 5 条」染成 success 绿，等于把问题类别显示成通过。
 * 2. 点「需要修正」胶囊 = 筛选表格 **并** 展开修正面板（点它的人下一步必然是修它）；
 *    只自动打开、不自动关闭，否则每点一次胶囊面板就闪一下。
 * 3. 「需要修正 N 条 = 四分区之和」这个等式要能被界面直接写出来（不是约等于），
 *    否则用户仍要自己把 5+1+180 加一遍。
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

/** 一行完整数据（数量、单价、金额自洽） */
function okRow(overrides: Record<string, unknown> = {}) {
  return {
    symbol: "002311",
    name: "海大集团",
    op_type: "sell",
    trade_date: "2026-10-28",
    quantity: 200,
    price: 47.97,
    amount: 9594,
    fee: 0,
    type: "stock",
    ...overrides
  };
}

/** 四类问题行各一条 + 一条正常 + 一条重复：fix 应为 4，complete 1，duplicate 1 */
function mixedRows() {
  return [
    okRow(),
    okRow({ is_duplicate: true }),
    okRow({ error: "交易日期无法解析" }),
    okRow({ symbol: "", name: "未命名基金" }), // 代码未匹配
    okRow({ quantity: 0 }), // 数量缺失 → 阻断
    okRow({ amount: 9700 }) // 差额 106 > fee 0 → 数据不一致
  ];
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

describe("分区 tag 颜色按问题性质定档，不比条数", () => {
  it("代码未匹配只有 5 条时是 warning，不是 success（旧实现在此返回绿）", () => {
    const w = setup([okRow()]);
    // 旧实现：getCategoryTagType('missingCode', 5) → success（5 ≤ 10 落最后一档）
    expect(w.getCategoryTagType("missingCode")).toBe("warning");
  });

  it("阻断类（解析错误 / 数量价格缺失）为 danger；可导入但需留意（不一致）为 warning", () => {
    const w = setup([okRow()]);
    expect(w.getCategoryTagType("error")).toBe("danger");
    expect(w.getCategoryTagType("missingQtyPrice")).toBe("danger");
    expect(w.getCategoryTagType("mismatch")).toBe("warning");
  });

  it("未知键回落 info，不抛错（逆回购等非问题分区）", () => {
    const w = setup([okRow()]);
    expect(w.getCategoryTagType("reverse_repo")).toBe("info");
  });
});

describe("点「需要修正」胶囊：筛选 + 展开面板", () => {
  it("筛选到 fix 且自动打开修正面板", () => {
    const w = setup(mixedRows());
    expect(w.showFixPanel.value).toBe(false);

    w.toggleCategoryFilter("fix");

    expect(w.tableStatusFilter.value).toBe("fix");
    expect(w.showFixPanel.value).toBe(true);
    // 打开时形态回到阈值判定（与 toggleFixPanel 一致），不残留上一轮的手动覆盖
    expect(w.fixModeOverride.value).toBeNull();
    expect(w.singleFixScope.value).toBe("all");
  });

  it("再点一次收起筛选，但面板保持打开（只自动开、不自动关）", () => {
    const w = setup(mixedRows());
    w.toggleCategoryFilter("fix");
    w.toggleCategoryFilter("fix");

    expect(w.tableStatusFilter.value).toBe("");
    expect(w.showFixPanel.value).toBe(true);
  });

  it("没有需修正行时点 fix 胶囊不打开空面板", () => {
    const w = setup([okRow()]);
    w.toggleCategoryFilter("fix");

    expect(w.summaryCounts.value.fix).toBe(0);
    expect(w.showFixPanel.value).toBe(false);
  });

  it("其它类别胶囊不会顺手打开面板", () => {
    const w = setup(mixedRows());
    w.toggleCategoryFilter("complete");
    expect(w.showFixPanel.value).toBe(false);

    w.toggleCategoryFilter("duplicate");
    expect(w.showFixPanel.value).toBe(false);
  });
});

describe("概览条等式与筛选复位", () => {
  it("「需要修正」= 四分区之和（等式成立，不是约等于）", () => {
    const w = setup(mixedRows());

    const b = w.fixBreakdown.value;
    const sectionSum = b.error + b.missingCode + b.missingQtyPrice + b.mismatch;

    expect(sectionSum).toBe(w.summaryCounts.value.fix);
    expect(b.error).toBe(1);
    expect(b.missingCode).toBe(1);
    expect(b.missingQtyPrice).toBe(1);
    expect(b.mismatch).toBe(1);
  });

  it("三胶囊之和恒等于总行数（重复行只计入 duplicate）", () => {
    const w = setup(mixedRows());
    const c = w.summaryCounts.value;

    // 基准取 previewData 本身，不取 totalRows：后者是解析计数 ref，靠多处赋值同步，
    // 概览条的「全部」条数因此由三类相加得出（见 SummaryPanel 的 totalCount）
    expect(c.complete + c.duplicate + c.fix).toBe(w.previewData.value.length);
  });

  it("「全部」胶囊清空类别筛选", () => {
    const w = setup(mixedRows());
    w.toggleCategoryFilter("complete");
    expect(w.tableStatusFilter.value).toBe("complete");

    w.expandAllData();

    expect(w.tableStatusFilter.value).toBe("");
    // 表格常驻（折叠按钮 2026-11-03 移除），这里只需确认筛选回退到全量
    expect(w.showProblemOnly.value).toBe(false);
  });
});
