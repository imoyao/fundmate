/**
 * 表头排序分发（2026-10-30 整组化后的判据）。
 *
 * ## 为什么必须有这个文件
 *
 * 「列上写了 sortable」与「点表头真的按这个指标排」是两件事，中间隔着 `onSortChange`。
 * 少接一次线，列定义照样全绿——这正是 #1331「标了 sortable 却查不到白名单」的形态：
 * **静默失效，无任何信号**。
 *
 * ## 钉什么
 *
 * | # | 判据 | 为什么值得钉 |
 * |---|---|---|
 * | 1 | 当日盈亏 → `data.setClientSort("day_pnl", …)`，**不**调后端 | 后端 `change_pct` 是上一交易日收盘算的，按它排 = 按昨天的涨幅排，与列里显示的今日实时值不是同一个数 |
 * | 2 | 口径 amount / pct 取不同的数 | 复合列两行是两个量（同样涨 1%，一万仓与百万仓差两个数量级）；#2641 只代理 change_pct，「按金额排序」根本不存在 |
 * | 3 | 最新价 → `setClientSort("current_price", …)`，取实时价、缺行情回落后端价、都没有给 null | 与 money renderer 同口径；给 0 会让「没行情」的行看起来像「价格跌到 0」 |
 * | 4 | 其余列 → `clearClientSort` + `handleSortChange(prop)` | 这些值后端就有，跨页一致由后端保证 |
 * | 5 | `order === null` → 必须落到后端清空 | 否则取消排序后表格停在上一轮的本地切片上 |
 * | 6 | **不再有「只排当前页」的分支** | 旧实现实时开启时只排当前页，第 2 页重新从头上开始 = 用户说的「顺序乱」 |
 *
 * ⚠️ `useWatchlistTable` 是 composable，构造时只做解构与 `computed` 定义（懒求值），
 * 故这里用最小桩对象即可驱动 `onSortChange`，不需要挂载组件。`useRouter` 在
 * 应用上下文外返回 `undefined`，本文件 mock 掉以免刷告警。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { watchlistColumnDefs } from "../columnDefs";
import type { DayPnlMetric } from "../dayPnl";
import { useWatchlistTable } from "../composables/useWatchlistTable";

function colDef(key: string) {
  const def = watchlistColumnDefs.find(d => d.key === key);
  if (!def) throw new Error(`${key} 列定义缺失`);
  return def;
}

interface RowLike {
  id: number;
  symbol: string;
  is_pinned?: boolean;
  current_price?: number | null;
  prev_close?: number | null;
  holding_quantity?: number | null;
}

function makeRow(
  id: number,
  symbol: string,
  extra: Partial<RowLike> = {}
): RowLike {
  return { id, symbol, ...extra };
}

type DayPnlResultLike = { value: number | null; ratio: number | null };

/**
 * 最小 options 桩。`dayPnlOf` 在这里按行返回预置结果，便于断言
 * 「金额口径取 value、涨幅口径取 ratio」。
 */
function setup({
  dayPnlMetric = "amount" as DayPnlMetric,
  quotes = {} as Record<string, { currentPrice: number; source: string }>,
  dayPnl = {} as Record<string, DayPnlResultLike>
} = {}) {
  const handleSortChange = vi.fn();
  const setClientSort = vi.fn();
  const clearClientSort = vi.fn();
  const getValuationItem = vi.fn((symbol: string) =>
    quotes[symbol] ? { symbol, ...quotes[symbol] } : undefined
  );

  const options = {
    groups: {},
    tags: {},
    toolbar: { batchMode: ref(false) },
    data: {
      items: ref([]),
      handleSortChange,
      setClientSort,
      clearClientSort,
      dayPnlMetric: ref(dayPnlMetric)
    },
    valuation: {
      realtimeEnabled: ref(true),
      getValuationItem,
      addedReturnPct: () => null,
      addedReturnAmount: () => null,
      dayPnlOf: (row: RowLike) =>
        dayPnl[row.symbol] ?? { value: null, ratio: null },
      marketValueRatio: () => null,
      trendMap: ref(new Map()),
      intradayMap: ref(new Map())
    },
    actions: {},
    activeCategory: ref(null),
    columnSettings: {
      visibleColumns: ref([
        colDef("day_pnl"),
        colDef("current_price"),
        colDef("holding_quantity")
      ])
    }
  };

  const table = useWatchlistTable(options as never);
  return { table, handleSortChange, setClientSort, clearClientSort };
}

describe("表头排序分发：吃实时价的列走客户端整组排序", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("当日盈亏：交给 setClientSort，**不再**把 change_pct 发给后端", () => {
    const { table, setClientSort, handleSortChange } = setup();

    table.onSortChange({ prop: "day_pnl", order: "descending" });

    expect(setClientSort).toHaveBeenCalledTimes(1);
    const [key, order] = setClientSort.mock.calls[0];
    expect(key).toBe("day_pnl");
    expect(order).toBe("desc");
    // 反例守卫：一旦退回后端排序，盘中就是「按昨天涨幅排」
    expect(handleSortChange).not.toHaveBeenCalled();
  });

  it("金额口径：取值是金额（value），不是涨跌幅", () => {
    const { table, setClientSort } = setup({
      dayPnlMetric: "amount",
      dayPnl: { A: { value: 100, ratio: 1.2 } }
    });
    table.onSortChange({ prop: "day_pnl", order: "descending" });
    const valueOf = setClientSort.mock.calls[0][2];
    expect(valueOf(makeRow(1, "A"))).toBe(100);
  });

  it("涨幅口径：取值是涨跌幅（ratio）——「今天谁涨得最凶」是另一个问题", () => {
    const { table, setClientSort } = setup({
      dayPnlMetric: "pct",
      dayPnl: { A: { value: 100, ratio: 1.2 } }
    });
    table.onSortChange({ prop: "day_pnl", order: "descending" });
    const valueOf = setClientSort.mock.calls[0][2];
    expect(valueOf(makeRow(1, "A"))).toBe(1.2);
  });

  it("当日盈亏缺值 → 取值 null（交给排序函数垫底，而不是当 0）", () => {
    const { table, setClientSort } = setup({
      dayPnl: { A: { value: null, ratio: null } }
    });
    table.onSortChange({ prop: "day_pnl", order: "descending" });
    const valueOf = setClientSort.mock.calls[0][2];
    expect(valueOf(makeRow(1, "A"))).toBeNull();
  });

  it("最新价：实时价优先；实时开或关都走客户端整组（同一套机制）", () => {
    const { table, setClientSort, handleSortChange } = setup({
      quotes: { A: { currentPrice: 12.5, source: "realtime" } }
    });

    table.onSortChange({ prop: "current_price", order: "ascending" });

    const [key, order] = setClientSort.mock.calls[0];
    expect(key).toBe("current_price");
    expect(order).toBe("asc");
    const valueOf = setClientSort.mock.calls[0][2];
    expect(valueOf(makeRow(1, "A", { current_price: 10 }))).toBe(12.5);
    expect(handleSortChange).not.toHaveBeenCalled();
  });

  it("最新价兜底：没拿到实时行情用后端静态价，两样都没有给 null", () => {
    const { table, setClientSort } = setup({
      quotes: { B: { currentPrice: 0, source: "static" } }
    });
    table.onSortChange({ prop: "current_price", order: "descending" });
    const valueOf = setClientSort.mock.calls[0][2];
    // 实时值为 0 且 source 不是 realtime → 回落后端静态价
    expect(valueOf(makeRow(1, "A", { current_price: 8 }))).toBe(8);
    expect(valueOf(makeRow(2, "B"))).toBeNull();
  });

  it("普通列（持有数量）：退出客户端模式并交给后端", () => {
    const { table, handleSortChange, clearClientSort } = setup();

    table.onSortChange({ prop: "holding_quantity", order: "descending" });

    expect(clearClientSort).toHaveBeenCalled();
    expect(handleSortChange).toHaveBeenCalledWith({
      prop: "holding_quantity",
      order: "descending"
    });
  });

  it("取消排序：先退出客户端模式，再让后端回默认序", () => {
    const { table, handleSortChange, clearClientSort, setClientSort } = setup();

    table.onSortChange({ prop: "day_pnl", order: null });

    expect(clearClientSort).toHaveBeenCalled();
    expect(handleSortChange).toHaveBeenCalledWith({
      prop: "day_pnl",
      order: null
    });
    expect(setClientSort).not.toHaveBeenCalled();
  });
});
