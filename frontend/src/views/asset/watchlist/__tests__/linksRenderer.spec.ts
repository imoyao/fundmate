/**
 * 自选「关联」列：分组 / 角标措辞 / 浮层结构（#2503）。
 *
 * 本文件钉的是**浮层结构与文案**而不是像素：分组是结构化的（两个区块各有标题与
 * 条目），拼成一句平铺文本会让「哪些能场内买、哪些只能场外申购」重新混在一起
 * ——那正是 #2503 要修的形态。
 *
 * ⚠️ 为什么测 `./linkGroups` 而不是直接调 `renderCell`：
 * vitest 环境是 node（无 DOM），而 `columnRenderers.tsx` 为了画单元格会 import
 * MoneyDisplay 等 `.vue` 组件，那条依赖链最终会初始化 router / supabase
 *（实测一路要求 VITE_SUPABASE_URL → VITE_ROUTER_HISTORY）。故把可测的整形逻辑
 * 留在纯模块里、这里直接测它；**ElTooltip 的 content slot 接线不在此覆盖**
 *（改动只是一行 `content: () => buildLinkTip(groups)`）。
 */

import { describe, expect, it } from "vitest";

import { watchlistColumnDefs } from "../columnDefs";
import {
  buildLinkTip,
  groupLinks,
  linkBadgeText,
  type WatchlistLinkItem
} from "../linkGroups";

function linksDef() {
  const def = watchlistColumnDefs.find(d => d.key === "links");
  if (!def) throw new Error("links 列定义缺失");
  return def;
}

function item(
  code: string,
  name: string | null,
  link_type: string
): WatchlistLinkItem {
  return { code, name, link_type };
}

/** 递归收集 VNode 树里的文本（children 可能是字符串 / 数组 / 单个 VNode）。 */
function collectText(node: unknown, out: string[] = []): string[] {
  if (node == null || typeof node === "boolean") return out;
  if (typeof node === "string" || typeof node === "number") {
    out.push(String(node));
    return out;
  }
  if (Array.isArray(node)) {
    node.forEach(n => collectText(n, out));
    return out;
  }
  const children = (node as { children?: unknown }).children;
  return children == null ? out : collectText(children, out);
}

function tipTexts(links: WatchlistLinkItem[]): string[] {
  return collectText(buildLinkTip(groupLinks(links)));
}

describe("关联列的适用范围（#2503 判据）", () => {
  it("覆盖场外基金：appliesTo 含 fund", () => {
    expect(linksDef().appliesTo).toContain("fund");
  });

  it("不新增列：关联列仍只有一个（列宽预算 ≤1040px）", () => {
    expect(watchlistColumnDefs.filter(d => d.key === "links")).toHaveLength(1);
  });
});

describe("分组", () => {
  it("两组并存时分成两个区块，组标题各带数量", () => {
    const texts = tipTexts([
      item("510300", "沪深300ETF", "index_etf"),
      item("110020", "易方达沪深300ETF联接", "etf_feeder"),
      item("000961", "天弘沪深300", "etf_feeder")
    ]);

    expect(texts).toContain("场内 ETF · 1");
    expect(texts).toContain("场外联接 · 2");
    expect(texts).toContain("易方达沪深300ETF联接（110020）");
    expect(texts).toContain("天弘沪深300（000961）");
    expect(texts).toContain("沪深300ETF（510300）");
  });

  it("空关联不产生任何分组（渲染层据此降级 —，不出现空浮层）", () => {
    expect(groupLinks([])).toEqual([]);
  });

  it("组内缺失名称时降级显示代码，不渲染 null / 不留空条目", () => {
    const texts = tipTexts([item("510300", null, "index_etf")]);
    expect(texts).toContain("510300");
    expect(texts.some(t => t.includes("null"))).toBe(false);
  });

  it("未知 link_type 落入兜底组而不消失", () => {
    const texts = tipTexts([item("999999", "未知关联", "some_new_type")]);
    expect(texts).toContain("其他关联 · 1");
    expect(texts).toContain("未知关联（999999）");
  });
});

describe("角标措辞", () => {
  it("场外联接行说清方向：对应场内 N", () => {
    const groups = groupLinks([
      item("510300", "沪深300ETF", "etf_feeder"),
      item("510500", "中证500ETF", "etf_feeder")
    ]);
    expect(linkBadgeText(groups, "fund")).toBe("对应场内 2");
  });

  it("指数行 / ETF 行按组并列：场内 N · 场外 M", () => {
    const groups = groupLinks([
      item("510300", "沪深300ETF", "index_etf"),
      item("110020", "易方达沪深300ETF联接", "etf_feeder")
    ]);
    expect(linkBadgeText(groups, "index")).toBe("场内 1 · 场外 1");
    expect(linkBadgeText(groups, "etf")).toBe("场内 1 · 场外 1");
  });

  it("只有一组时不带分隔符", () => {
    const groups = groupLinks([item("510300", "沪深300ETF", "index_etf")]);
    expect(linkBadgeText(groups, "index")).toBe("场内 1");
  });
});
