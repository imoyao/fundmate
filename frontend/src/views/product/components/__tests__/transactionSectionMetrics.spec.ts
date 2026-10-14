/**
 * 「交易记录」区块渐进披露的判定（#2160）。
 *
 * 首版把 `per_page: 10` 写死在组件里、**没有任何提示**，是详情页 17 个区块里唯一的
 * 静默截断——用户把「前 10 条」当成「全部」。这类缺陷没有报错、截图上也看不出来，
 * 只能靠断言钉住。
 *
 * 钉四件容易被改坏的事：
 * 1. 按钮按 `total` 出，不按已取量出（折叠态已取量恒为 10，拿它判断必然出错）；
 * 2. 折叠只渲染前 10 行、展开渲染全部；
 * 3. 展开只补取一次，且上限封顶（不为「展开全部」拉全量）；
 * 4. 「查看全部流水」只在展开态出现，且只在真看不全时出现。
 *
 * 反向验证：把 `needToggle` 改成 `rows.length > PREVIEW_SIZE` → 用例 1 转红；
 * 把 `shouldFetchMore` 改成 `!expanded` → 用例 3 的「不重复取」转红。
 */
import { describe, it, expect } from "vitest";
import {
  PREVIEW_SIZE,
  EXPAND_SIZE,
  needToggle,
  visibleRows,
  shouldFetchMore,
  showsPartial
} from "../transactionSectionMetrics";

/** n 条流水；只用来数长度，内容用序号占位 */
const rows = (n: number): number[] =>
  Array.from({ length: n }, (_, i) => i + 1);

describe("needToggle：按钮按总量出，不按已取量出", () => {
  it("恰好等于预览行数时**不出**按钮（「展开全部 10 条」是纯噪声）", () => {
    expect(needToggle(PREVIEW_SIZE)).toBe(false);
  });

  it("比预览行数少 1 时不出按钮", () => {
    expect(needToggle(PREVIEW_SIZE - 1)).toBe(false);
  });

  it("比预览行数多 1 时出按钮（阈值必须是 > 而非 >=）", () => {
    expect(needToggle(PREVIEW_SIZE + 1)).toBe(true);
  });

  it("0 条不出按钮（空态由 hasTransactions 分支接管，不该叠一个按钮）", () => {
    expect(needToggle(0)).toBe(false);
  });
});

describe("visibleRows：折叠只渲染前 10 行", () => {
  it("折叠态截断到 10 行", () => {
    expect(visibleRows(rows(47), false)).toHaveLength(PREVIEW_SIZE);
  });

  it("折叠态取的是**前** 10 行（不是后 10 行）", () => {
    expect(visibleRows(rows(47), false)).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8, 9, 10
    ]);
  });

  it("展开态渲染全部（已取到多少就是多少，不二次截断）", () => {
    expect(visibleRows(rows(47), true)).toHaveLength(47);
  });

  it("总量不超过预览量时折叠态也返回全部 —— 不能把 8 条截成别的数", () => {
    expect(visibleRows(rows(8), false)).toHaveLength(8);
  });

  it("不修改入参（slice 必须是拷贝，否则折叠会吃掉原始数据）", () => {
    const input = rows(47);
    visibleRows(input, false);
    expect(input).toHaveLength(47);
  });
});

describe("shouldFetchMore：展开时只补取一次，且上限封顶", () => {
  it("折叠态只取 10 条时展开需要补取", () => {
    expect(shouldFetchMore(PREVIEW_SIZE, 47)).toBe(true);
  });

  it("已取满 EXPAND_SIZE 时**不再取**（否则每次点展开都发一次请求）", () => {
    expect(shouldFetchMore(EXPAND_SIZE, 47)).toBe(false);
  });

  it("已取够总量时不再取（总量本来就小于上限）", () => {
    expect(shouldFetchMore(20, 20)).toBe(false);
  });

  it("总量超上限时目标封顶在 EXPAND_SIZE，不为「展开全部」拉全量", () => {
    // 500 条的高频交易者：展开只补到 50，剩下的交给 TransactionList
    expect(shouldFetchMore(0, 500)).toBe(true);
    expect(Math.min(500, EXPAND_SIZE)).toBe(EXPAND_SIZE);
    expect(shouldFetchMore(EXPAND_SIZE, 500)).toBe(false);
  });
});

describe("showsPartial：「查看全部流水」只在展开态且真看不全时出现", () => {
  it("折叠态不出现（多数用户用不到这个出口，摆出来只是噪声）", () => {
    expect(showsPartial(false, 10, 500)).toBe(false);
  });

  it("展开后仍看不全时出现", () => {
    expect(showsPartial(true, EXPAND_SIZE, 500)).toBe(true);
  });

  it("展开后已全部拿到时不出现（出口指向的页面不会有更多）", () => {
    expect(showsPartial(true, 20, 20)).toBe(false);
  });

  it("折叠态即使只取到 10 条也不出现 —— 判据是「展开后仍看不全」，不是「没取完」", () => {
    // 这条最容易写错：把「已取量 < 总量」直接当判据，会在折叠态就摆出链接
    expect(showsPartial(false, PREVIEW_SIZE, 500)).toBe(false);
  });
});
