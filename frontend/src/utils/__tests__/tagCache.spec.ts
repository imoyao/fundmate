/**
 * 标签缓存清洗单测。
 *
 * 背景（2026-10-30 用户反馈 + 截图）：顶部标签栏里出现一个**没有文字的空白标签块**
 * ——宽度只剩关闭按钮、鼠标能点、控制台报 `Cannot read properties of undefined
 * (reading 'length')`。成因是 `multiTagsCache` 开启后标签数组跨版本存活，历史条目
 * 没有 `meta.title`；而旧渲染 `{{ item.meta.title }}` 与旧判空
 * `tagVal?.meta?.title.length` 都不会剔除它。
 */
import { describe, it, expect } from "vitest";
import { sanitizeTags, isRenderableTag, type TagLike } from "../tagCache";

const ok: TagLike = {
  path: "/watchlist",
  name: "Watchlist",
  meta: { title: "我的自选" }
};

describe("isRenderableTag", () => {
  it("正常标签可渲染", () => {
    expect(isRenderableTag(ok)).toBe(true);
  });

  it("没有 meta / 没有 title / 标题为空白 → 不可渲染（否则就是一个空白块）", () => {
    expect(isRenderableTag({ path: "/a", name: "A" })).toBe(false);
    expect(isRenderableTag({ path: "/a", meta: {} })).toBe(false);
    expect(isRenderableTag({ path: "/a", meta: { title: "" } })).toBe(false);
    expect(isRenderableTag({ path: "/a", meta: { title: "   " } })).toBe(false);
    expect(isRenderableTag({ path: "/a", meta: { title: null } })).toBe(false);
  });

  it("没有 path 的标签点不动，也不可渲染", () => {
    expect(isRenderableTag({ meta: { title: "无路径" } })).toBe(false);
    expect(isRenderableTag({ path: "", meta: { title: "空路径" } })).toBe(
      false
    );
  });

  it("null / undefined 不抛错", () => {
    expect(isRenderableTag(null)).toBe(false);
    expect(isRenderableTag(undefined)).toBe(false);
  });
});

describe("sanitizeTags", () => {
  it("剔除无标题条目，保留其余（模拟一份历史脏缓存）", () => {
    const cached: TagLike[] = [
      { path: "/welcome", name: "Welcome", meta: { title: "首页" } },
      {
        path: "/asset/portfolios",
        name: "PortfolioList",
        meta: { title: "投资组合" }
      },
      // ↓ 截图里那个空白标签：有 path、无标题
      { path: "/asset/strategies", name: "Strategies", meta: {} },
      { path: "/asset/recurring", name: "AssetRecurring" },
      ok
    ];
    expect(sanitizeTags(cached).map(t => t.path)).toEqual([
      "/welcome",
      "/asset/portfolios",
      "/watchlist"
    ]);
  });

  it("同 path + query + params 去重，只留第一条", () => {
    const list: TagLike[] = [
      ok,
      { ...ok },
      {
        path: "/fund/004369",
        meta: { title: "产品详情" },
        query: { from: "a" }
      },
      {
        path: "/fund/004369",
        meta: { title: "产品详情" },
        query: { from: "a" }
      },
      {
        path: "/fund/004369",
        meta: { title: "产品详情" },
        query: { from: "b" }
      }
    ];
    expect(sanitizeTags(list).length).toBe(3);
  });

  it("非数组（缓存被写成对象/字符串）→ 空数组，不抛错", () => {
    expect(sanitizeTags(null)).toEqual([]);
    expect(sanitizeTags(undefined)).toEqual([]);
    expect(sanitizeTags({} as any)).toEqual([]);
  });

  it("判据非空转：全脏的缓存清洗后为空，调用方可回退到固定标签", () => {
    expect(sanitizeTags([{ path: "/x" }, { meta: { title: "" } }])).toEqual([]);
  });
});
