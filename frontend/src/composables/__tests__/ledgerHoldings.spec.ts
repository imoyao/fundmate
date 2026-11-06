import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed } from "vue";
import type { LedgerHoldingRow } from "../ledger/types";

/**
 * #2948（D89）：`useLedgerHoldings` 的行为判据。
 *
 * 这一刀搬的是「分页状态 + 一次取数」，风险全在**行为细节**上——两处取舍是既有契约，
 * 搬错不会编译报错，只会让用户看到「页码跳回去」或「持仓全没了」：
 *
 * 1. `holdingsPage` 在**请求之前**赋值（分页器立即回显目标页，失败也不回滚）
 * 2. 失败只提示、**不清空列表**（网络抖动不该变成「持仓全没了」）
 *
 * 另有取数口径三条：默认第一页 / `per_page=20` / 搜索词 trim 后为空则**不传** search
 * 字段（传空串会让后端 LIKE `%%`，语义上等价但会多走一次过滤分支）。
 */

const mocks = vi.hoisted(() => ({
  getLedgerPositions: vi.fn(),
  elMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() }
}));

vi.mock("@/api/ledger", () => ({
  getLedgerPositions: mocks.getLedgerPositions
}));

vi.mock("element-plus", () => ({ ElMessage: mocks.elMessage }));

import { useLedgerHoldings } from "../ledger/useLedgerHoldings";

const ROWS: LedgerHoldingRow[] = [
  { id: 1, symbol: "000001", market_value: 100 } as LedgerHoldingRow
];

function makeApi(id = "12") {
  return useLedgerHoldings(computed(() => id));
}

/** 取第 n 次（默认最后一次）调用的入参 */
function lastCall() {
  const calls = mocks.getLedgerPositions.mock.calls;
  return calls[calls.length - 1] as [number, Record<string, unknown>];
}

describe("#2948 D89 useLedgerHoldings 取数口径", () => {
  beforeEach(() => {
    mocks.getLedgerPositions.mockReset();
    mocks.elMessage.error.mockReset();
    mocks.getLedgerPositions.mockResolvedValue({
      data: { items: ROWS, total: 42 }
    });
  });

  it("初始态：第一页 / 每页 20 / 空列表 / 搜索为空", () => {
    const api = makeApi();
    expect(api.holdingsPage.value).toBe(1);
    expect(api.holdingsPageSize).toBe(20);
    expect(api.holdingsList.value).toEqual([]);
    expect(api.holdingsTotal.value).toBe(0);
    expect(api.holdingsSearch.value).toBe("");
  });

  it("默认取第一页，账户 id 转数字，per_page 固定 20，空搜索不传 search", async () => {
    const api = makeApi("12");
    await api.loadHoldings();

    const [id, params] = lastCall();
    expect(id).toBe(12);
    expect(params).toEqual({ page: 1, per_page: 20, search: undefined });
  });

  it("指定页码时按该页取数", async () => {
    const api = makeApi();
    await api.loadHoldings(3);

    expect(mocks.getLedgerPositions).toHaveBeenCalledTimes(1);
    expect(lastCall()[1]).toMatchObject({ page: 3 });
    expect(api.holdingsPage.value).toBe(3);
  });

  it("搜索词 trim 后随请求下发", async () => {
    const api = makeApi();
    api.holdingsSearch.value = "  华夏  ";
    await api.loadHoldings(2);

    expect(lastCall()[1]).toMatchObject({ page: 2, search: "华夏" });
  });

  it("纯空格搜索词等同于没搜（不传 search）", async () => {
    const api = makeApi();
    api.holdingsSearch.value = "   ";
    await api.loadHoldings();

    expect(lastCall()[1].search).toBeUndefined();
  });

  it("成功时用响应覆盖列表与总数", async () => {
    const api = makeApi();
    await api.loadHoldings();

    expect(api.holdingsList.value).toEqual(ROWS);
    expect(api.holdingsTotal.value).toBe(42);
  });

  it("响应缺字段时落成空列表 / 0，而不是 undefined", async () => {
    mocks.getLedgerPositions.mockResolvedValue({ data: {} });
    const api = makeApi();
    await api.loadHoldings();

    // 模板里有 `holdingsTotal > 0`：undefined 会让它静默恒假（整块操作栏消失）
    expect(api.holdingsList.value).toEqual([]);
    expect(api.holdingsTotal.value).toBe(0);
  });
});

describe("#2948 D89 useLedgerHoldings 两处既有取舍（搬错了不报错，只出错）", () => {
  beforeEach(() => {
    mocks.getLedgerPositions.mockReset();
    mocks.elMessage.error.mockReset();
  });

  it("页码在请求返回之前就更新（分页器立即回显，不跳回去）", async () => {
    let settle: (v: unknown) => void = () => {};
    mocks.getLedgerPositions.mockReturnValue(
      new Promise(resolve => {
        settle = resolve;
      })
    );

    const api = makeApi();
    const pending = api.loadHoldings(3);

    // 请求还没回，页码必须已经是 3——否则慢网下分页器会先跳回 1 再跳回 3
    expect(api.holdingsPage.value).toBe(3);

    settle({ data: { items: ROWS, total: 42 } });
    await pending;
    expect(api.holdingsPage.value).toBe(3);
  });

  it("请求失败：提示一次、列表与总数保持上一页、页码不回滚", async () => {
    mocks.getLedgerPositions.mockResolvedValueOnce({
      data: { items: ROWS, total: 42 }
    });
    const api = makeApi();
    await api.loadHoldings();
    expect(api.holdingsTotal.value).toBe(42);

    mocks.getLedgerPositions.mockRejectedValueOnce(new Error("网络断了"));
    await api.loadHoldings(2);

    expect(mocks.elMessage.error).toHaveBeenCalledTimes(1);
    expect(mocks.elMessage.error).toHaveBeenCalledWith("持仓加载失败");
    // 留着上一页数据，好过让一次抖动变成「持仓全没了」
    expect(api.holdingsList.value).toEqual(ROWS);
    expect(api.holdingsTotal.value).toBe(42);
    // 页码停在用户点的页（已知取舍，别当 bug 顺手"修"）
    expect(api.holdingsPage.value).toBe(2);
  });
});
