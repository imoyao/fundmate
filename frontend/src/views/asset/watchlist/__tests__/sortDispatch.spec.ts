/**
 * 表头排序分发（#2641「删列不删排序能力」的运行时判据）。
 *
 * ## 为什么必须有这个文件
 *
 * `dayPnl.spec.ts` 只钉住**列定义**（`sortable: "custom"` + `sortBy: "change_pct"`）。
 * 但「列上写了 `sortBy`」与「点表头真的把 `sort_by=change_pct` 发出去」是两件事——
 * 中间还隔着一层 `onSortChange`。少接一次线，列定义照样全绿，后端照样收不到，
 * 而这正是 #1331「标了 sortable 却查不到白名单」的形态：**静默失效，无任何信号**。
 *
 * ## 钉什么
 *
 * 1. **非实时路径**：`day_pnl` 的表头点击 → `data.handleSortChange` 收到
 *    `prop: "change_pct"`（不是 `"day_pnl"`）。后者后端查不到，会静默按默认序返回。
 * 2. **实时路径**：沿用既有客户端排序分支（`realtimeField`），只排当前页，
 *    **不**调后端——与原来点「今日涨跌幅」表头的行为一致。
 * 3. **实时路径的兜底**：某个标的没有实时估值项时，兜底值取 `row[sortBy]`
 *    （`row.change_pct`），而不是派生列的 `row.day_pnl`（恒 `undefined` ⇒ 0，
 *    会让缺实时值的行被排到一端，看起来像「它们跌停了」）。
 * 4. **普通列不受影响**：`current_price` 仍按自身 key 走，`sortBy` 不改变既有行为。
 * 5. **取消排序**：`order === null` 时必须落到 `handleSortChange`（清空排序回默认），
 *    不能被实时分支吞掉——否则取消排序后表格停在客户端重排过的顺序。
 *
 * ⚠️ `useWatchlistTable` 是 composable，构造时只做解构与 `computed` 定义（懒求值），
 * 故这里用最小桩对象即可驱动 `onSortChange`，不需要挂载组件。`useRouter` 在
 * 应用上下文外返回 `undefined`，本文件 mock 掉以免刷告警。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { watchlistColumnDefs } from "../columnDefs";
import { useWatchlistTable } from "../composables/useWatchlistTable";

function colDef(key: string) {
  const def = watchlistColumnDefs.find(d => d.key === key);
  if (!def) throw new Error(`${key} 列定义缺失`);
  return def;
}

interface RowLike {
  id: number;
  symbol: string;
  change_pct: number | null;
}

function makeRow(
  id: number,
  symbol: string,
  changePct: number | null
): RowLike {
  return { id, symbol, change_pct: changePct };
}

/**
 * 最小 options 桩：`useWatchlistTable` 构造期只解构这些引用，
 * 其余（renderCtx / 行 hover）都在 computed 或事件回调里懒执行。
 */
function setup({
  realtimeEnabled = false,
  rows = [] as RowLike[],
  realtimeItems = [] as Array<{ symbol: string; changePct?: number }>
} = {}) {
  const items = ref(rows) as unknown as { value: RowLike[] };
  const handleSortChange = vi.fn();
  const getValuationItem = vi.fn((symbol: string) =>
    realtimeItems.find(it => it.symbol === symbol)
  );

  const options = {
    groups: {},
    tags: {},
    toolbar: { batchMode: ref(false) },
    data: { items, handleSortChange },
    valuation: {
      realtime: { items: ref(realtimeItems) },
      realtimeEnabled: ref(realtimeEnabled),
      getValuationItem,
      addedReturnPct: () => null,
      addedReturnAmount: () => null,
      dayPnlOf: () => null,
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
  return { table, items, handleSortChange, getValuationItem };
}

describe("表头排序分发：当日盈亏列代理到后端 change_pct（#2641）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("非实时路径：把 sort_by 代理成 change_pct，而不是派生列 key", () => {
    const { table, handleSortChange } = setup();

    table.onSortChange({ prop: "day_pnl", order: "descending" });

    expect(handleSortChange).toHaveBeenCalledTimes(1);
    expect(handleSortChange).toHaveBeenCalledWith({
      prop: "change_pct",
      order: "descending"
    });
    // 反例守卫：写成 prop: "day_pnl" 后端查不到白名单 ⇒ 静默按默认序返回
    expect(handleSortChange.mock.calls[0][0].prop).not.toBe("day_pnl");
  });

  it("实时路径：按实时涨跌幅客户端排序，不动后端（仅当前页，沿用 #1333 既有行为）", () => {
    const { table, items, handleSortChange } = setup({
      realtimeEnabled: true,
      rows: [makeRow(1, "A", 1), makeRow(2, "B", 3), makeRow(3, "C", -2)],
      realtimeItems: [
        { symbol: "A", changePct: -1.5 },
        { symbol: "B", changePct: 2.5 },
        { symbol: "C", changePct: 0.5 }
      ]
    });

    table.onSortChange({ prop: "day_pnl", order: "descending" });

    expect(handleSortChange).not.toHaveBeenCalled();
    expect(items.value.map(r => r.symbol)).toEqual(["B", "C", "A"]);
  });

  it("实时路径兜底取 row[sortBy]（change_pct），不是 row.day_pnl", () => {
    // A 有实时值、B 没有：B 必须按它的 change_pct（+10）排，而不是 0 ——
    // 取 row.day_pnl 会得到 undefined ⇒ 0，B 会被挤到最下面，看起来像「跌了」。
    const { table, items, handleSortChange } = setup({
      realtimeEnabled: true,
      rows: [makeRow(1, "A", 1), makeRow(2, "B", 10)],
      realtimeItems: [{ symbol: "A", changePct: 5 }]
    });

    table.onSortChange({ prop: "day_pnl", order: "descending" });

    expect(handleSortChange).not.toHaveBeenCalled();
    expect(items.value.map(r => r.symbol)).toEqual(["B", "A"]);
  });

  it("普通列不受 sortBy 影响：current_price 仍按自身 key 走后端", () => {
    const { table, handleSortChange } = setup();

    table.onSortChange({ prop: "current_price", order: "ascending" });

    expect(handleSortChange).toHaveBeenCalledWith({
      prop: "current_price",
      order: "ascending"
    });
  });

  it("实时关闭时「最新价」也落后端（#2641 修的既有缺陷：原分支不看实时开关）", () => {
    // 实时关闭 ⇒ 列里显示的就是后端静态值 ⇒ 没有理由只排当前页。
    // 原实现 `if (def?.realtimeField && order)` 会让它永远客户端排，翻页即错。
    const { table, items, handleSortChange } = setup({
      realtimeEnabled: false,
      rows: [makeRow(1, "A", 1), makeRow(2, "B", 3)]
    });

    table.onSortChange({ prop: "current_price", order: "descending" });

    expect(handleSortChange).toHaveBeenCalledWith({
      prop: "current_price",
      order: "descending"
    });
    expect(items.value.map(r => r.symbol)).toEqual(["A", "B"]); // 未被客户端重排
  });

  it("取消排序（order=null）必须落到后端清空，不能被实时分支吞掉", () => {
    const { table, items, handleSortChange } = setup({
      realtimeEnabled: true,
      rows: [makeRow(1, "A", 1), makeRow(2, "B", 3)],
      realtimeItems: [
        { symbol: "A", changePct: 1 },
        { symbol: "B", changePct: 3 }
      ]
    });

    table.onSortChange({ prop: "day_pnl", order: null });

    expect(handleSortChange).toHaveBeenCalledWith({
      prop: "change_pct",
      order: null
    });
    // 客户端顺序不被重排（取消排序后交给后端默认序，不是停在上一轮客户端排序）
    expect(items.value.map(r => r.symbol)).toEqual(["A", "B"]);
  });
});
