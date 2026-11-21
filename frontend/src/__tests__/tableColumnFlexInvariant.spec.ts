// frontend/src/__tests__/tableColumnFlexInvariant.spec.ts
//
// #3210 收尾：列宽由配置驱动（写在 *.ts 里）的表，静态守卫看不见——它读的是模板属性
// `:width="def.width"`，解析不到真值。`scripts/guard_table_columns.py` 因此把这几个文件
// 登记进 `CONFIG_TABLE_JUDGE`，并要求**必须有本文件承接**（登记了但没有判据 = 把跳过写成通过）。
//
// 这里直接 import 配置本体，用与守卫同一条判据：
//
//   命中 = 弹性列恰好 1 个，且固定列 ≥ 1 个
//
// 依据：EP 的 `updateColumnsWidth()` **只把「不带数字 width」的列纳入容器余量分配**；
// 只留一个弹性列时，整条余量都灌给它，其余列一动不动（#3208 实测首列占 36%~76%）。
//
// 为什么不在守卫里解析 TS：正则猜 `def.width` 会在 spread、辅助函数、条件分支上错判，
// 而**错判比不判更贵**——它会把人骗去改本来正确的表。

import { describe, expect, it } from "vitest";

import { getDefaultVisibleColumns } from "@/views/asset/watchlist/columnDefs";
import { tableColumns as rankingColumns } from "@/views/asset/fund-ranking/rankingColumns";
import { columnsForMode } from "@/views/asset/investment/import/composables/importWizardData";

/** 只关心宽度：这些配置的公共子集（三份定义各有各的字段） */
interface WidthDef {
  width?: number;
  minWidth?: number;
}

function classify(defs: readonly WidthDef[]): { flex: number; fixed: number } {
  // 「有数字 width」= 固定列；其余（写了 minWidth 或两者都没写）= 弹性列，与 EP 一致
  const flex = defs.filter(d => typeof d.width !== "number").length;
  return { flex, fixed: defs.length - flex };
}

function isSingleFlexWithFixed(defs: readonly WidthDef[]): boolean {
  const { flex, fixed } = classify(defs);
  return flex === 1 && fixed >= 1;
}

// 被 `scripts/guard_table_columns.py` 的 CONFIG_TABLE_JUDGE 登记的三张表。
// 预览表有两套列（基金 / 股票），故 3 个文件 = 4 份配置。
const CASES: ReadonlyArray<{ name: string; defs: readonly WidthDef[] }> = [
  {
    name: "自选页 WatchlistTableSection（冻结列 width / 其余 minWidth）",
    defs: getDefaultVisibleColumns()
  },
  {
    name: "基金排行 FundRankingTable（接口里没有 width，只有 minWidth）",
    defs: rankingColumns
  },
  {
    name: "导入预览 PreviewTable · 基金模式",
    defs: columnsForMode(true)
  },
  {
    name: "导入预览 PreviewTable · 股票模式",
    defs: columnsForMode(false)
  }
];

describe("配置驱动的表格：列宽不得「单弹性列独吃余量」", () => {
  it("覆盖张数与守卫登记一致（删掉一条用例会在这里红）", () => {
    // 守卫侧登记 3 个文件；预览表两种模式各一套列 ⇒ 4 份配置。
    // 增减表格时同步改这里与 CONFIG_TABLE_JUDGE，两边对不上就说明有一侧漏了。
    expect(CASES).toHaveLength(4);
  });

  for (const { name, defs } of CASES) {
    it(`${name}：弹性列 ≥ 2 或全固定`, () => {
      // 空配置会让下面那条断言恒真（假绿），先钉住「确实取到了列」
      expect(defs.length).toBeGreaterThan(0);
      const { flex, fixed } = classify(defs);
      expect(
        isSingleFlexWithFixed(defs),
        `弹性列 ${flex} / 固定列 ${fixed}：只留一个弹性列时，容器余量会全部灌给它`
      ).toBe(false);
    });
  }

  it("判据本身有失败态（否则上面的全绿只证明没扫到东西）", () => {
    // #3208 修复前的真实写法：首列 min-width，其余全 width
    expect(
      isSingleFlexWithFixed([{ minWidth: 150 }, { width: 120 }, { width: 100 }])
    ).toBe(true);
    // #3208 的修法：两列以上 min-width ⇒ 余量按比例分摊
    expect(
      isSingleFlexWithFixed([
        { minWidth: 150 },
        { minWidth: 120 },
        { width: 100 }
      ])
    ).toBe(false);
  });
});
