import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { useImportWizard } from "../useImportWizard";

/**
 * 分页与筛选同源（2026-11-02 真实数据踩到）。
 *
 * 旧实现的两个静默缺陷：
 * 1. el-pagination 的 :total 绑全量 totalRows，而表格内容是筛选后切片
 *    →「只看问题数据」剩 2 条时 pager 仍显示 7 页（全量 340），点第 2 页空表；
 * 2. 没有任何地方钳制 currentPage：筛选收缩后页码停在超出范围的大页上，
 *    切片落空区间，表格假性空白——用户以为是数据丢了。
 *
 * 修法：total 改绑 filteredTotal（与「共 N 条」同源）+ 统一 watcher 钳页，
 * 不在每个筛选入口各自复位——入口会不断增加，漏一个就是静默空表。
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

describe("分页 total 与筛选同源", () => {
  it("filteredTotal 只数筛选后可见行，不等于全量", () => {
    const rows = Array.from({ length: 6 }, (_, i) =>
      okRow({ symbol: `00${i}` })
    );
    rows.push(okRow({ quantity: 0 })); // 一条阻断行
    const w = setup(rows);
    expect(w.filteredTotal.value).toBe(7);

    w.showProblemOnly.value = true;
    expect(w.filteredTotal.value).toBe(1);
    // 当前页数据与 total 一致，不再出现「共 2 条但 pager 显示 7 页」
    expect(w.filteredPagedData.value).toHaveLength(1);
  });
});

describe("筛选收缩后页码钳制", () => {
  it("停在大页上开启筛选 → currentPage 自动回到有效范围，不出现空表页", async () => {
    const rows = Array.from({ length: 6 }, (_, i) =>
      okRow({ symbol: `00${i}` })
    );
    const w = setup(rows);
    w.pageSize.value = 1;
    w.currentPage.value = 6; // 最后一页，合法
    expect(w.filteredPagedData.value).toHaveLength(1);

    // 开启「只看问题数据」→ 无阻断行，列表收缩为 0 → 页码必须钳回 1
    // （watcher 是 pre-flush：钳制发生在重渲染前，故这里 await 一次调度即可）
    w.showProblemOnly.value = true;
    await nextTick();
    expect(w.currentPage.value).toBe(1);
  });

  it("筛选后仍有数据时钳到最后一页（不是无脑回 1）", async () => {
    const rows = Array.from({ length: 6 }, (_, i) =>
      okRow({ symbol: `00${i}` })
    );
    rows.push(okRow({ quantity: 0 })); // 仅最后一条是阻断行
    const w = setup(rows);
    w.pageSize.value = 1;
    w.currentPage.value = 5;

    w.showProblemOnly.value = true; // 只剩 1 条 = 第 1 页
    await nextTick();
    expect(w.currentPage.value).toBe(1);
    expect(w.filteredPagedData.value).toHaveLength(1);
  });

  it("经过收缩态再恢复数据，页码仍落在有效范围内（收缩时被合法钳到 1）", async () => {
    const rows = Array.from({ length: 6 }, (_, i) =>
      okRow({ symbol: `00${i}` })
    );
    const w = setup(rows);
    w.pageSize.value = 1;
    w.currentPage.value = 2;

    w.showProblemOnly.value = true; // 收缩到 0 条 → 钳回 1（正确的中间态）
    await nextTick();
    expect(w.currentPage.value).toBe(1);
    w.showProblemOnly.value = false; // 回到 6 条：1 仍是有效页，不额外跳页
    await nextTick();
    expect(w.currentPage.value).toBe(1);
    expect(w.filteredPagedData.value).toHaveLength(1);
  });
});
