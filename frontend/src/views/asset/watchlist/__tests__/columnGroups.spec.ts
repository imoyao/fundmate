/**
 * 列设置面板的分组口径（#2650 回归）。
 *
 * ## 钉什么
 *
 * 1. **每个可隐藏列都必须至少出现在一个分组里**——这是本文件的核心判据。
 *    #2650 把 `trend.scope` 改成 `"category"` 后，「通用字段」组按 `scope === "mixed"`
 *    取列，把 `trend` 滤掉了；它的分组又是 `general`，不属于任何品类组，于是
 *    **设置面板里彻底找不到「走势」**。PR 里承诺的「混合视图可在列设置开启」是空路径，
 *    用户实测反馈才暴露。
 * 2. **通用组按分组归类取列，与 `scope` 无关**——即使某列 scope 是 category，
 *    只要归组 general 就必须可勾（`shown` 语义保证勾上后任何视图都显示）。
 * 3. **品类组 = 通用列 + 该组专属列**——用户在「基金」导航下也能配齐通用列。
 */
import { describe, expect, it } from "vitest";

import { getColumnGroup, watchlistColumnDefs } from "../columnDefs";
import { buildColumnGroups, type ColumnGroupSection } from "../columnGroups";

const hideable = watchlistColumnDefs.filter(d => d.hideable);
const sections: ColumnGroupSection[] = buildColumnGroups(hideable);

function keysOf(section: ColumnGroupSection) {
  return section.cols.map(c => c.key);
}

describe("列设置分组：不允许有「表格里有、设置里没有」的列", () => {
  it("每个可隐藏列至少出现在一个分组里（#2650 的 trend 就是被这条漏掉的）", () => {
    const covered = new Set(sections.flatMap(s => s.cols.map(c => c.key)));
    const missing = hideable.map(c => c.key).filter(k => !covered.has(k));
    expect(
      missing,
      `这些列在列设置里找不到入口：${missing.join(", ")}`
    ).toEqual([]);
  });

  it("分组里不出现不可隐藏列（它们是固定列，勾了也没用）", () => {
    const fixed = watchlistColumnDefs.filter(d => !d.hideable).map(d => d.key);
    const listed = sections.flatMap(s => s.cols.map(c => c.key));
    expect(listed.filter(k => fixed.includes(k))).toEqual([]);
  });
});

describe("通用字段组：按 group 归属收列，不看 scope", () => {
  const general = sections.find(s => s.key === "general");

  it("走势列在「通用字段」组里（历史回归点）", () => {
    expect(general).toBeDefined();
    expect(keysOf(general!)).toContain("trend");
  });

  it("所有归组 general 的可隐藏列都能勾到", () => {
    const expected = hideable
      .filter(c => getColumnGroup(c.key) === "general")
      .map(c => c.key);
    expect(keysOf(general!).sort()).toEqual(expected.sort());
  });

  it("通用组不因 scope 变化而缩水：scope 与 group 是两套口径", () => {
    // 造一个「scope=category 但归组 general」的列，模拟 #2650 当时的 trend。
    // 分组必须收它——显示与否由 isVisibleInView 决定，与能否勾选无关。
    const fake = hideable
      .filter(c => c.key === "trend")
      .map(c => ({
        ...c,
        scope: "category" as const
      }));
    const groups = buildColumnGroups([
      ...hideable.filter(c => c.key !== "trend"),
      ...fake
    ]);
    const generalKeys = keysOf(groups.find(g => g.key === "general")!);
    expect(generalKeys).toContain("trend");
  });
});

describe("品类组：通用列 + 该组专属列", () => {
  const generalKeys = keysOf(sections.find(s => s.key === "general")!);

  it("每个非通用组都包含全部通用列", () => {
    const others = sections.filter(s => s.key !== "general");
    expect(others.length).toBeGreaterThan(0);
    for (const s of others) {
      const keys = keysOf(s);
      for (const k of generalKeys) {
        expect(keys, `「${s.title}」组缺通用列 ${k}`).toContain(k);
      }
    }
  });

  it("专属列只出现在自己的组里，不串组", () => {
    for (const s of sections.filter(s => s.key !== "general")) {
      for (const col of s.cols) {
        const group = getColumnGroup(col.key);
        expect(
          group === "general" || group === s.key,
          `${col.key}（group=${group}）不该出现在「${s.title}」组`
        ).toBe(true);
      }
    }
  });
});
