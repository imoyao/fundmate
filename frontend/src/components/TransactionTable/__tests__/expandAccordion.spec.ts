/**
 * 行展开手风琴（#2749 关联反馈）。
 *
 * 这些用例钉的是**行为**，不是实现：
 * - 展开新行 → 旧行必须自动关闭（同时只留一个详情面板）；
 * - 展开新行时，刚展开的那一行**不能**被顺手关掉。
 *
 * 第二条是重点：`element-plus` 的 `toggleRowExpansion` 会**同步**再 emit 一次
 * `expand-change`（`store/expand.mjs`），上一版实现死在这个重入上——
 * 用户点开一行，它立刻自己关掉。用例里用一个「模拟 element-plus 行为」的假表格
 * 把这条同步重入复现出来，不靠注释说明，靠断言钉住。
 */
import { describe, expect, it, vi } from "vitest";
import {
  createExpandAccordion,
  planAccordion,
  type ExpandableTable
} from "../expandAccordion";
import type { TransactionRow } from "../model";

const row = (id: number): TransactionRow =>
  ({ id, type: "buy" }) as TransactionRow;

/**
 * 模拟 `el-table` 的展开存储（`store/expand.mjs`）：
 * - `expandRows` 保存已展开的行；
 * - `toggleRowExpansion` 改完状态后**同步** emit `expand-change`，
 *   第二个参数是「当前全部已展开的行」（`expandRows.slice()`）。
 */
function createFakeTable() {
  const expandRows: TransactionRow[] = [];
  const listeners: Array<
    (r: TransactionRow, expanded: TransactionRow[]) => void
  > = [];

  const table: ExpandableTable & {
    expandRows: TransactionRow[];
    onChange: (
      cb: (r: TransactionRow, expanded: TransactionRow[]) => void
    ) => void;
  } = {
    expandRows,
    onChange(cb) {
      listeners.push(cb);
    },
    toggleRowExpansion(target: TransactionRow, expanded: boolean) {
      const index = expandRows.indexOf(target);
      if (expanded && index === -1) expandRows.push(target);
      else if (!expanded && index !== -1) expandRows.splice(index, 1);
      // 同步重入：状态改完立刻 emit，与 element-plus 一致
      for (const cb of listeners) cb(target, expandRows.slice());
    }
  };
  return table;
}

describe("planAccordion", () => {
  it("刚展开的行 → 标记为展开，并把其它已展开行列为待收起", () => {
    const a = row(1);
    const b = row(2);
    const plan = planAccordion(b, [a, b]);
    expect(plan.isExpanded).toBe(true);
    expect(plan.toCollapse).toEqual([a]);
  });

  it("刚收起的行 → 不算展开，且不碰其它行", () => {
    const a = row(1);
    const b = row(2);
    // a 刚被收起：已展开列表里只剩 b
    const plan = planAccordion(a, [b]);
    expect(plan.isExpanded).toBe(false);
    expect(plan.toCollapse).toEqual([]);
  });

  it("只有一行展开时没有其它行要收", () => {
    const a = row(1);
    const plan = planAccordion(a, [a]);
    expect(plan.isExpanded).toBe(true);
    expect(plan.toCollapse).toEqual([]);
  });

  it("空列表 = 全部收起，不算展开", () => {
    expect(planAccordion(row(1), []).isExpanded).toBe(false);
  });
});

describe("createExpandAccordion", () => {
  it("展开新行 → 旧行自动关闭（同时只留一个详情面板）", () => {
    const table = createFakeTable();
    const onExpand = vi.fn();
    const { handleExpandChange } = createExpandAccordion({
      getTable: () => table,
      onExpand
    });
    table.onChange(handleExpandChange);

    const a = row(1);
    const b = row(2);

    table.toggleRowExpansion(a, true);
    expect(table.expandRows).toEqual([a]);
    expect(onExpand).toHaveBeenCalledTimes(1);

    table.toggleRowExpansion(b, true);
    // a 被自动收起，只剩 b 展开
    expect(table.expandRows).toEqual([b]);
    expect(onExpand).toHaveBeenCalledTimes(2);
    expect(onExpand).toHaveBeenLastCalledWith(b);
  });

  it("展开新行时，刚展开的那一行不会被同步重入误关（#2749 的真 bug）", () => {
    const table = createFakeTable();
    const onExpand = vi.fn();
    const { handleExpandChange } = createExpandAccordion({
      getTable: () => table,
      onExpand
    });
    table.onChange(handleExpandChange);

    const a = row(1);
    const b = row(2);

    table.toggleRowExpansion(a, true);
    table.toggleRowExpansion(b, true);

    // 关键断言：b 仍然展开着。若重入处理错了，这里会是空数组
    expect(table.expandRows).toEqual([b]);
  });

  it("收起一行 → 不通知容器取详情（否则每次收起都白跑一次接口）", () => {
    const table = createFakeTable();
    const onExpand = vi.fn();
    const { handleExpandChange } = createExpandAccordion({
      getTable: () => table,
      onExpand
    });
    table.onChange(handleExpandChange);

    const a = row(1);
    table.toggleRowExpansion(a, true);
    expect(onExpand).toHaveBeenCalledTimes(1);

    table.toggleRowExpansion(a, false);
    expect(onExpand).toHaveBeenCalledTimes(1);
    expect(table.expandRows).toEqual([]);
  });

  it("连开三行 → 只留最后一行展开", () => {
    const table = createFakeTable();
    const onExpand = vi.fn();
    const { handleExpandChange } = createExpandAccordion({
      getTable: () => table,
      onExpand
    });
    table.onChange(handleExpandChange);

    const a = row(1);
    const b = row(2);
    const c = row(3);

    table.toggleRowExpansion(a, true);
    table.toggleRowExpansion(b, true);
    table.toggleRowExpansion(c, true);

    expect(table.expandRows).toEqual([c]);
  });

  it("表格实例还没就绪时，不报错、也不取详情", () => {
    const onExpand = vi.fn();
    const { handleExpandChange } = createExpandAccordion({
      getTable: () => null,
      onExpand
    });
    const a = row(1);
    expect(() => handleExpandChange(a, [a])).not.toThrow();
    expect(onExpand).toHaveBeenCalledWith(a);
  });

  it("树形态（第二个参数是 boolean）→ 展开才通知", () => {
    const onExpand = vi.fn();
    const { handleExpandChange } = createExpandAccordion({
      getTable: () => null,
      onExpand
    });
    const a = row(1);
    handleExpandChange(a, true);
    expect(onExpand).toHaveBeenCalledWith(a);
    handleExpandChange(a, false);
    expect(onExpand).toHaveBeenCalledTimes(1);
  });
});
