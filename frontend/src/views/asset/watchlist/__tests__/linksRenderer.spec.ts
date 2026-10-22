/**
 * 自选「关联」列（renderer: links）单测 —— #2503
 *
 * 覆盖三件事：
 * 1. **分组语义**：行品类 × `link_type` → 组标题 / 角标短词。这是本卡的核心，
 *    也是最容易写错的地方（`index_etf` 在指数行是「场内 ETF」，在 ETF 行是「跟踪指数」）；
 * 2. **浮层条目**：`名称（代码）` 文案、同组去重、超长截断（实测一个指数最多挂 35 只 ETF）；
 * 3. **接线守卫（源码断言）**：`columnDefs.ts` 的 `links` 列真的覆盖了 `fund`、
 *    `columnRenderers.tsx` 真的用了本模块——纯函数单测绿了但没人调用，是本仓
 *    反复出现过的假绿形态（见 AGENTS.md「守门要分两层」）。
 *
 * 为什么不 mount 组件：本仓单测环境是 `node` 且未装 `@vue/test-utils` / jsdom
 * （`vitest.config.ts` 的 `environment: "node"`），组件级断言无处可跑；
 * 因此渲染分支刻意做薄——所有文案与分组都在 `linkGroups.ts`（纯函数）里，
 * renderer 只做「VNode 拼装」。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  LINK_GROUP_MAX_ITEMS,
  groupLinks,
  linkBadgeText,
  linkItemText,
  splitForTooltip,
  type WatchlistLink
} from "../linkGroups";

const link = (
  code: string,
  name: string | null,
  link_type: string | null
): WatchlistLink => ({ code, name, link_type });

describe("groupLinks（行品类 × link_type 决定组标题）", () => {
  it("links 为空 → 无分组（渲染器据此出 `—`，不渲染空浮层）", () => {
    expect(groupLinks([], "index")).toEqual([]);
    expect(groupLinks(undefined, "fund")).toEqual([]);
    expect(linkBadgeText([])).toBe("");
  });

  it("指数行：index_etf 的另一侧是场内 ETF", () => {
    const groups = groupLinks(
      [link("510300", "沪深300ETF", "index_etf")],
      "index"
    );
    expect(groups).toHaveLength(1);
    expect(groups[0].title).toBe("场内 ETF");
    expect(groups[0].short).toBe("场内");
    expect(linkBadgeText(groups)).toBe("场内 1");
  });

  it("ETF 行：index_etf 的另一侧是**跟踪指数**，不能标成场内 ETF", () => {
    const groups = groupLinks([link("000300", "沪深300", "index_etf")], "etf");
    expect(groups[0].title).toBe("跟踪指数");
    expect(groups[0].short).toBe("指数");
    expect(linkBadgeText(groups)).toBe("指数 1");
  });

  it("场外联接行：etf_feeder 的另一侧是「对应场内 ETF」", () => {
    const groups = groupLinks(
      [link("159101", "港股通科技ETF", "etf_feeder")],
      "fund"
    );
    expect(groups).toHaveLength(1);
    expect(groups[0].title).toBe("对应场内 ETF");
    expect(groups[0].short).toBe("对应场内");
    expect(linkBadgeText(groups)).toBe("对应场内 1");
  });

  it("ETF 行两类关系并存 → 两组，指数在前、场外在后", () => {
    const groups = groupLinks(
      [
        link("025805", "港股通科技ETF联接A", "etf_feeder"),
        link("000300", "沪深300", "index_etf"),
        link("025806", "港股通科技ETF联接C", "etf_feeder")
      ],
      "etf"
    );
    expect(groups.map(g => g.title)).toEqual(["跟踪指数", "场外联接"]);
    expect(groups.map(g => g.items.length)).toEqual([1, 2]);
    expect(linkBadgeText(groups)).toBe("指数 1 · 场外 2");
  });

  it("未知 link_type 排在已知两类之后，标题退化为中性「其他关联」", () => {
    const groups = groupLinks(
      [
        link("A1", "某标的A", "mystery"),
        link("000300", "沪深300", "index_etf")
      ],
      "etf"
    );
    expect(groups.map(g => g.title)).toEqual(["跟踪指数", "其他关联"]);
  });

  it("同组内按 code 去重（双向查下 A→B / B→A 同时存在时不重复列出）", () => {
    const groups = groupLinks(
      [
        link("510300", "沪深300ETF", "index_etf"),
        link("510300", "沪深300ETF", "index_etf")
      ],
      "index"
    );
    expect(groups[0].items).toHaveLength(1);
    expect(linkBadgeText(groups)).toBe("场内 1");
  });

  it("缺 code 的脏数据被跳过，不产生空条目", () => {
    const groups = groupLinks(
      [
        link("", "空代码", "index_etf"),
        link("510300", "沪深300ETF", "index_etf")
      ],
      "index"
    );
    expect(groups[0].items).toHaveLength(1);
  });
});

describe("linkItemText / splitForTooltip（浮层条目）", () => {
  it("有条目用 `名称（代码）`，缺名退化为代码，不编造名称", () => {
    expect(linkItemText(link("510300", "沪深300ETF", "index_etf"))).toBe(
      "沪深300ETF（510300）"
    );
    expect(linkItemText(link("510300", null, "index_etf"))).toBe("510300");
  });

  it("超过上限的组截断，并给出剩余数量（指数最多挂 35 只 ETF，全列会撑破浮层）", () => {
    const items = Array.from({ length: LINK_GROUP_MAX_ITEMS + 3 }, (_, i) =>
      link(String(510300 + i), `ETF${i}`, "index_etf")
    );
    const [group] = groupLinks(items, "index");
    const [shown, rest] = splitForTooltip(group);
    expect(shown).toHaveLength(LINK_GROUP_MAX_ITEMS);
    expect(rest).toBe(3);
    // 角标仍报全量：截断只影响浮层陈列，不影响「一共几只」
    expect(linkBadgeText([group])).toBe(`场内 ${items.length}`);
  });
});

describe("接线守卫（纯函数不会被调用 → 本组断言拦这种假绿）", () => {
  const read = (rel: string): string =>
    readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

  it("columnDefs.ts 的 links 列 appliesTo 覆盖 fund（场外联接行才有入口）", () => {
    const source = read("../columnDefs.ts");
    const start = source.indexOf('key: "links"');
    expect(start).toBeGreaterThan(-1);
    // 只截到本列定义结束附近；appliesTo 紧跟 key，不会串列
    const block = source.slice(start, start + 1200);
    expect(block).toContain('appliesTo: ["index", "etf", "fund"]');
  });

  it("columnRenderers.tsx 的 renderLinks 真的走 groupLinks + linkBadgeText", () => {
    const source = read("../columnRenderers.tsx");
    const start = source.indexOf("const renderLinks");
    const end = source.indexOf("const RENDERER_ADVISOR_RETURNS");
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const block = source.slice(start, end);
    expect(block).toContain("groupLinks(links, assetTypeOf(props.row))");
    expect(block).toContain("linkBadgeText(groups)");
    // 无关联仍走 `—`（全表约定），不得渲染空浮层
    expect(block).toContain('class: "link-empty"');
  });
});
