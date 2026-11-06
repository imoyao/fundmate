/**
 * 自选「整组客户端排序」判据（`clientSort.ts`）。
 *
 * 钉四件事，全部是 2026-10-30 用户实测踩到的形态：
 * 1. 降序 = 从大到小（「今天涨得最多的在最上面」），升序反之；
 * 2. **置顶行恒在最前**——与后端 `apply_user_sort` 同口径，否则同一张表换个指标排，
 *    置顶行就跳到中间去（用户会以为置顶功能坏了）；
 * 3. **缺值（null / NaN）恒排末尾**，上升下降都是——缺数据被当 0 会把没数据的行
 *    摆在「涨/跌 0%」的位置，看起来像真实的持平；
 * 4. 同值稳定：实时价 30s 一个 tick，同值行不能在每次重排时互换位置（视觉抖动）。
 */
import { describe, expect, it } from "vitest";

import { sortRowsForClient } from "../clientSort";

interface Row {
  symbol: string;
  is_pinned?: boolean;
  value: number | null;
}

const rows: Row[] = [
  { symbol: "A", value: 10 },
  { symbol: "B", value: -5 },
  { symbol: "C", value: 30 },
  { symbol: "D", value: null },
  { symbol: "E", value: 10 }
];

const valueOf = (row: Row) => row.value;
const symbols = (list: Row[]) => list.map(r => r.symbol);

describe("sortRowsForClient：整组排序", () => {
  it("降序（用户点「当日盈亏」第一眼要看的顺序）", () => {
    const sorted = sortRowsForClient(rows, { order: "desc", valueOf });
    expect(symbols(sorted)).toEqual(["C", "A", "E", "B", "D"]);
  });

  it("升序", () => {
    const sorted = sortRowsForClient(rows, { order: "asc", valueOf });
    expect(symbols(sorted)).toEqual(["B", "A", "E", "C", "D"]);
  });

  it("缺值恒排末尾（升序也不许顶到最前）", () => {
    expect(
      symbols(sortRowsForClient(rows, { order: "asc", valueOf })).pop()
    ).toBe("D");
    expect(
      symbols(sortRowsForClient(rows, { order: "desc", valueOf })).pop()
    ).toBe("D");
  });

  it("NaN 与 null 同待遇（都算缺值）", () => {
    const withNaN: Row[] = [
      { symbol: "A", value: 1 },
      { symbol: "B", value: Number.NaN }
    ];
    expect(
      symbols(sortRowsForClient(withNaN, { order: "desc", valueOf }))
    ).toEqual(["A", "B"]);
  });

  it("置顶行恒前置（与后端 apply_user_sort 同口径）", () => {
    const withPinned: Row[] = [
      { symbol: "A", value: 10 },
      { symbol: "B", value: -5, is_pinned: true },
      { symbol: "C", value: 30 },
      { symbol: "P2", value: 1, is_pinned: true }
    ];
    // 置顶内部仍按指标序（B:-5 < P2:1），非置顶在后（C:30 > A:10）
    expect(
      symbols(sortRowsForClient(withPinned, { order: "desc", valueOf }))
    ).toEqual(["P2", "B", "C", "A"]);
  });

  it("同值稳定：保持原有相对顺序（实时 tick 重排不抖动）", () => {
    expect(
      symbols(sortRowsForClient(rows, { order: "desc", valueOf }))
    ).toEqual(["C", "A", "E", "B", "D"]);
    // A 在 E 之前 —— 两者都是 10，顺序由下标决定而不是随机
    const again = sortRowsForClient(rows, { order: "desc", valueOf });
    expect(symbols(again)).toEqual(
      symbols(sortRowsForClient(rows, { order: "desc", valueOf }))
    );
  });

  it("不改输入数组", () => {
    const input = [...rows];
    sortRowsForClient(input, { order: "desc", valueOf });
    expect(symbols(input)).toEqual(["A", "B", "C", "D", "E"]);
  });
});
