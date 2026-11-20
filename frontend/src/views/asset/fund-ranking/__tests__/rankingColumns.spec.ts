import { describe, expect, it } from "vitest";

import {
  FUND_COL_WIDTH,
  RANK_COL_WIDTH,
  columnGroups,
  tableColumns
} from "../rankingColumns";

/**
 * 表头结构判据（#3200 迁 el-table 后，从 e2e 前移到单测）。
 *
 * 迁移前：`<th colspan>` 是模板里手写的 `g.keys.length`，列却是 `tableColumns`
 * 平铺渲染 —— 两条线各走各的，分组键漏一个，表头就与数据列错位，所以 e2e 要断言
 * 「colspan 之和 == 指标列数」。
 *
 * 迁移后：表格只按 `columnGroups.keys` 取列渲染，colspan 由 el-table 按子列数
 * 自动得出 —— 于是「colspan 之和 == 列数」变成恒真，e2e 那条断言失去判别力。
 * 会错的地方换了位置：**keys 漏掉 / 多出一列时，那列会从表头里整块消失**，
 * 页面上不报错、数据接口也照常返回。判据因此钉在这里：
 *
 * 1. 分组 keys 扁平化后与 `tableColumns` 的 key 序列**完全相同**（同序、全覆盖、无重复）；
 * 2. 列宽合计压在设计预算 1132px 内，且每列装得下「表头文字 + 排序三角」。
 */

describe("同类优选列定义的结构不变量", () => {
  it("分组 keys 与列定义同序全覆盖（漏一列 = 表头少一列，且无声）", () => {
    const flat = columnGroups.flatMap(g => g.keys);

    expect(flat).toEqual(tableColumns.map(c => c.key));
    // 重复键会让同一列渲染两遍、colspan 虚高
    expect(new Set(flat).size).toBe(flat.length);
  });

  it("列宽合计在 1132px 预算内，且每列容得下表头文字 + 排序三角", () => {
    const fixed = RANK_COL_WIDTH + FUND_COL_WIDTH;
    const total = fixed + tableColumns.reduce((sum, c) => sum + c.minWidth, 0);

    // design.md「冻结列与横向滚动规范」：默认可见列总宽 ≤ 1132px
    expect(total).toBeLessThanOrEqual(1132);

    for (const col of tableColumns) {
      // 13px 字号 × 汉字数 + 24 内边距 + 16 排序三角；低于此值表头会被省略号截断
      expect(col.minWidth).toBeGreaterThanOrEqual(col.label.length * 13 + 40);
    }
  });
});
