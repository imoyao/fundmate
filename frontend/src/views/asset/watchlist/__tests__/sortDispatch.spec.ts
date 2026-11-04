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
 * | 2 | 口径 amount / ratio 取不同的数 | 复合列两行是两个量（同样涨 1%，一万仓与百万仓差两个数量级）；#2641 只代理 change_pct，「按金额排序」根本不存在 |
 * | 3 | 最新价 → `setClientSort("current_price", …)`，取实时价、缺行情回落后端价、都没有给 null | 与 money renderer 同口径；给 0 会让「没行情」的行看起来像「价格跌到 0」 |
 * | 4 | 其余列 → `clearClientSort` + `handleSortChange(prop)` | 这些值后端就有，跨页一致由后端保证 |
 * | 5 | `order === null` → 必须落到后端清空 | 否则取消排序后表格停在上一轮的本地切片上 |
 * | 6 | **不再有「只排当前页」的分支** | 旧实现实时开启时只排当前页，第 2 页重新从头上开始 = 用户说的「顺序乱」 |
 * | 7 | 持仓收益 / 持仓市值走**后端**，但字段随口径切换 | 两列主行取自 positions 快照，后端排的就是列里的数；「金额 / 收益率（占比）」是库里两个不同的排序键 |
 * | 8 | 空仓行（数量 <= 0）的持仓收益给 null | 与 renderer 同判据；留 0 会让空仓行按「收益 0」排进队首 |
 *
 * ⚠️ `useWatchlistTable` 是 composable，构造时只做解构与 `computed` 定义（懒求值），
 * 故这里用最小桩对象即可驱动 `onSortChange`，不需要挂载组件。`useRouter` 在
 * 应用上下文外返回 `undefined`，本文件 mock 掉以免刷告警。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { watchlistColumnDefs } from "../columnDefs";
import type { SortMetric } from "../sortMetric";
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
  position_market_value?: number | null;
  holding_pnl?: number | null;
  holding_pnl_percent?: number | null;
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
 * 「金额口径取 value、比例口径取 ratio」；口径（`sortMetrics`）按列 key 预置。
 */
function setup({
  metrics = {} as Record<string, SortMetric>,
  quotes = {} as Record<string, { currentPrice: number; source: string }>,
  dayPnl = {} as Record<string, DayPnlResultLike>,
  marketValueRatio = () => null as number | null
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
      sortMetricOf: (key: string): SortMetric => metrics[key] ?? "amount"
    },
    valuation: {
      realtimeEnabled: ref(true),
      getValuationItem,
      addedReturnPct: () => null,
      addedReturnAmount: () => null,
      dayPnlOf: (row: RowLike) =>
        dayPnl[row.symbol] ?? { value: null, ratio: null },
      marketValueRatio,
      trendMap: ref(new Map()),
      intradayMap: ref(new Map())
    },
    actions: {},
    activeCategory: ref(null),
    columnSettings: {
      visibleColumns: ref([
        colDef("day_pnl"),
        colDef("current_price"),
        colDef("holding_quantity"),
        colDef("position_market_value"),
        colDef("holding_pnl")
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
      dayPnl: { A: { value: 100, ratio: 1.2 } }
    });
    table.onSortChange({ prop: "day_pnl", order: "descending" });
    const valueOf = setClientSort.mock.calls[0][2];
    expect(valueOf(makeRow(1, "A"))).toBe(100);
  });

  it("涨幅口径：取值是涨跌幅（ratio）——「今天谁涨得最凶」是另一个问题", () => {
    const { table, setClientSort } = setup({
      metrics: { day_pnl: "ratio" },
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

/**
 * 持仓市值 / 持仓收益：两列主行取自 positions 快照，后端排的就是列里的数，
 * 故仍走后端排序，「金额 / 比例」靠**换排序字段**实现（不是换取值函数）。
 */
describe("复合列走后端：排序字段随口径切换", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("持仓收益·金额口径 → 后端 holding_pnl，且先退出客户端整组模式", () => {
    const { table, handleSortChange, clearClientSort, setClientSort } = setup();

    table.onSortChange({ prop: "holding_pnl", order: "descending" });

    expect(setClientSort).not.toHaveBeenCalled();
    expect(clearClientSort).toHaveBeenCalled();
    expect(handleSortChange).toHaveBeenCalledWith({
      prop: "holding_pnl",
      order: "descending"
    });
  });

  it("持仓收益·收益率口径 → 后端 holding_pnl_percent（**不是**同一个字段）", () => {
    const { table, handleSortChange } = setup({
      metrics: { holding_pnl: "ratio" }
    });

    table.onSortChange({ prop: "holding_pnl", order: "ascending" });

    expect(handleSortChange).toHaveBeenCalledWith({
      prop: "holding_pnl_percent",
      order: "ascending"
    });
  });

  it("持仓市值·占比口径 → 后端 position_market_value（与金额同序，字段名由列定义声明）", () => {
    const { table, handleSortChange } = setup({
      metrics: { position_market_value: "ratio" }
    });

    table.onSortChange({ prop: "position_market_value", order: "descending" });

    expect(handleSortChange).toHaveBeenCalledWith({
      prop: "position_market_value",
      order: "descending"
    });
  });

  it("普通列没有 ratioSortBy → 字段不随口径变化（口径是复合列专属概念）", () => {
    const { table, handleSortChange } = setup({
      metrics: { holding_quantity: "ratio" }
    });

    table.onSortChange({ prop: "holding_quantity", order: "descending" });

    expect(handleSortChange).toHaveBeenCalledWith({
      prop: "holding_quantity",
      order: "descending"
    });
  });
});
