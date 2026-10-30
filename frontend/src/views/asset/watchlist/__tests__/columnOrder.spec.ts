/**
 * 自选表头列序回归判据（`columnOrder.ts`）+ 默认列序口径（2026-10-30 重排）。
 *
 * ## 为什么要有这个文件
 *
 * 「表头同一列出现两次」是**静默失效**：没有任何断言会因此变红，只有用户肉眼发现
 * （2026-10-30 实测：走势 / 持有数量 / 持仓市值 / 添加后涨幅 / 持仓收益 各两遍，
 * 当日盈亏一前一后）。根因是持久化的 `order` 只含**当时可见**的列（7~8 个 key），
 * 旧实现把它当全量顺序按槽位 shift、队列空后保留原位 ⇒ 同一列既占别人槽位又留原生位。
 *
 * 本文件钉两件事：
 * 1) `rebuildColumnOrder` 的输出**等长且 key 唯一**（任意输入都不重复、不丢列）；
 * 2) 默认列序口径（当日变动 → 价格 → 走势 → 持仓规模），防「重排」被静默改回去。
 *
 * 含**变异探针**：把旧算法就地复现一遍，确认它在同一输入下真的会重复——
 * 否则「修复被回退但测试仍绿」（旧实现换成新实现后用例全过，说明用例没测到点上）。
 */
import { describe, expect, it } from "vitest";

import { watchlistColumnDefs, type ColumnDef } from "../columnDefs";
import { rebuildColumnOrder } from "../columnOrder";

const keysOf = (defs: ColumnDef[]) => defs.map(d => d.key);
const defaults = () => watchlistColumnDefs;

/**
 * 用户坏缓存的真实形态：`order` 只有当时可见的 7 列
 * （含被显式开启的 `added_return`），而可拖拽槽位约 50 个。
 */
const PARTIAL_ORDER = [
  "current_price",
  "day_pnl",
  "trend",
  "holding_quantity",
  "position_market_value",
  "added_return",
  "holding_pnl"
];

/** 变异探针：2026-10-30 修复前 `orderedColumns` 的算法（部分顺序当全量用 + 槽位 shift） */
function legacyOrder(defs: ColumnDef[], order: string[]): ColumnDef[] {
  const orderIndex = new Map(order.map((k, i) => [k, i]));
  const draggables = defs
    .filter(d => d.draggable && orderIndex.has(d.key))
    .sort((a, b) => orderIndex.get(a.key)! - orderIndex.get(b.key)!);
  const queue = [...draggables];
  return defs.map(d => (d.draggable ? (queue.shift() ?? d) : d));
}

describe("rebuildColumnOrder：部分顺序不能当全量用（表头重复列回归）", () => {
  it("未排序（空 order）时原样返回默认定义", () => {
    const defs = defaults();
    expect(rebuildColumnOrder(defs, [])).toBe(defs);
  });

  it("旧算法在同一输入下确实产生重复列（变异探针）", () => {
    const legacyKeys = keysOf(legacyOrder(defaults(), PARTIAL_ORDER));
    // 旧实现：结果等长，但 key 有重复 ⇒ 有列出现两次
    expect(legacyKeys.length).toBe(defaults().length);
    expect(new Set(legacyKeys).size).toBeLessThan(legacyKeys.length);
  });

  it("新算法：结果等长、key 唯一、不丢列", () => {
    const defs = defaults();
    const result = rebuildColumnOrder(defs, PARTIAL_ORDER);
    const keys = keysOf(result);
    expect(result).toHaveLength(defs.length);
    expect(new Set(keys).size).toBe(keys.length); // 无重复
    expect(new Set(keys)).toEqual(new Set(keysOf(defs))); // 无丢列
  });

  it("用户排过的列按 order 顺序排在前面", () => {
    const keys = keysOf(rebuildColumnOrder(defaults(), PARTIAL_ORDER));
    expect(keys.filter(k => PARTIAL_ORDER.includes(k))).toEqual(PARTIAL_ORDER);
  });

  it("没排过的可拖拽列按默认顺序补在队尾（不插回各自原生槽位）", () => {
    const defs = defaults();
    const onlyOne = ["holding_pnl"];
    const keys = keysOf(rebuildColumnOrder(defs, onlyOne));
    // [0]=_selection、[1]=product 是固定列；拖拽区首位 = 用户排过的那一列
    expect(keys.slice(0, 2)).toEqual(["_selection", "product"]);
    expect(keys[2]).toBe("holding_pnl");

    const draggables = defs.filter(d => d.draggable).map(d => d.key);
    const rest = keys.slice(3); // 末位是右固定列 _actions
    expect(rest[rest.length - 1]).toBe("_actions");
    expect(rest.slice(0, -1)).toEqual(
      draggables.filter(k => k !== "holding_pnl")
    );
  });

  it("非拖拽列（固定列 / 内置列）位置恒不变", () => {
    const defs = defaults();
    const result = rebuildColumnOrder(defs, PARTIAL_ORDER);
    defs.forEach((d, i) => {
      if (!d.draggable) expect(result[i].key).toBe(d.key);
    });
  });

  it("order 里的未知 key / 重复 key / 非拖拽 key 一律忽略，且不挤掉别的列", () => {
    const defs = defaults();
    const dirty = [
      "product", // 非拖拽（左冻结）
      "_actions", // 非拖拽（右冻结）
      "no_such_column", // 定义里已删除
      "day_pnl",
      "day_pnl", // 重复
      "current_price"
    ];
    const keys = keysOf(rebuildColumnOrder(defs, dirty));
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys).toHaveLength(defs.length);
    // 只保留合法的拖拽 key，且保持首次出现顺序
    expect(keys.slice(2, 4)).toEqual(["day_pnl", "current_price"]);
  });

  it("order 列出全部可拖拽列时，结果顺序与 order 完全一致", () => {
    const defs = defaults();
    const full = defs
      .filter(d => d.draggable)
      .map(d => d.key)
      .reverse();
    const keys = keysOf(rebuildColumnOrder(defs, full));
    expect(keys).toEqual(["_selection", "product", ...full, "_actions"]);
  });
});

describe("默认列序（2026-10-30 重排：当日变动 → 价格 → 走势 → 持仓规模）", () => {
  const mixedDefaultKeys = watchlistColumnDefs
    .filter(
      d => d.key !== "_selection" && d.scope === "mixed" && !d.defaultHidden
    )
    .map(d => d.key);

  it("当日盈亏紧跟代码/名称，最新价其次，持仓三列殿后", () => {
    expect(mixedDefaultKeys).toEqual([
      "product",
      "day_pnl",
      "current_price",
      "trend",
      "holding_quantity",
      "position_market_value",
      "holding_pnl",
      "_actions"
    ]);
  });

  it("当日盈亏不再排在数据列末尾（用户反馈「默认排得比较靠后」）", () => {
    const idx = mixedDefaultKeys.indexOf("day_pnl");
    expect(idx).toBeGreaterThan(0);
    expect(idx).toBeLessThan(3);
  });
});
