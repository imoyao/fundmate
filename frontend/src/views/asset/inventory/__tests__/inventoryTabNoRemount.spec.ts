import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * 盘点页两条防回潮判据：切大类**不整页重挂载**、资产表列口径（名称 / 操作列）。
 *
 * ## 为什么需要（2026-11-11 实测，用户报「点上面的卡片整页刷新」）
 *
 * 布局层 `layout/components/lay-content/index.vue` 用 `route.fullPath` 作
 * `<component :key>`，因此页面里一句 `watch(activeCategory, () => router.replace({ query }))`
 * 就足以让整页重挂载：顶部 6 张大类卡重建、`onMounted` 的 `fetchData()` 连同
 * 汇总 / 分布 / 持仓分页 / 分类资产全套请求重跑。用户看到的就是「点一下卡片整页闪一下」。
 *
 * 同一根因在 `reconcile-workbench`（#2706）已经踩过一次并固化成「查询参数只读不写」，
 * 本页却又写回去了 ⇒ 光在注释里写「不要这么做」不足以拦住下一次，必须落判据。
 *
 * ## 判据口径
 *
 * 读源码、**剥注释后**匹配（同 `components/__tests__/assetEditDialogName.spec.ts`）：
 * 注释里出现 `router.replace({ query })` 不算违规，否则「写明不要这么做」反倒把自己判红。
 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

function readSource(relPath: string): string {
  return stripComments(readFileSync(new URL(relPath, import.meta.url), "utf8"));
}

/**
 * 抽出所有 `router.replace(...)` / `router.push(...)` 的实参原文。
 *
 * 不用 `\{[^}]*\}` 这类正则：实参里常有嵌套对象（`push({ name, query: helper({...}) })`），
 * 正则会在第一个内层 `}` 处截断，把「带 name 的跳转」误读成「只带 query」。
 * 这里按括号配对取完整实参，判据才咬得准。
 */
function routerCallArgs(src: string): string[] {
  const out: string[] = [];
  const re = /router\.(?:replace|push)\(/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) {
    const start = m.index + m[0].length;
    let depth = 0;
    let i = start;
    for (; i < src.length; i += 1) {
      const ch = src[i];
      if (ch === "(" || ch === "{" || ch === "[") depth += 1;
      else if (ch === ")" || ch === "}" || ch === "]") {
        if (depth === 0) break;
        depth -= 1;
      }
    }
    out.push(src.slice(start, i));
  }
  return out;
}

/**
 * 违规形态：**不带 `path` / `name` 的 router 跳转**。
 *
 * 只带 `query` 的 `router.replace({ query })` 改的是**当前路由**的 fullPath
 * （布局层 `:key` 随之变化 ⇒ 整页重挂载）；带 `path` / `name` 的是正常的「去别的页面」，
 * 本页 `askAbout()` 就属于后者（跳账本精灵并预填），不能一起判红。
 */
function inPlaceQueryCalls(src: string): string[] {
  return routerCallArgs(src)
    .map(arg => arg.trim())
    .filter(arg => arg.startsWith("{"))
    .filter(arg => !/(?:^|[\s,{])(?:name|path)\s*:/.test(arg));
}

const pageSource = readSource("../index.vue");
const categoryTable = readSource("../components/CategoryAssetTable.vue");
const otherTable = readSource("../components/OtherInvestmentTable.vue");
const tableBaseline = readSource("../../../../style/el-table.css");

describe("盘点页切大类不整页刷新（#2706 同根因）", () => {
  it("页内切大类不得改写 query —— 改写即整页重挂载", () => {
    expect(inPlaceQueryCalls(pageSource)).toEqual([]);
  });

  it("判据自己咬得住历史 bug（否则它是「永远绿」的假守卫）", () => {
    // 修复前的真实写法，必须被判红
    expect(
      inPlaceQueryCalls(
        "watch(activeCategory, v => router.replace({ query: { ...route.query, tab: v } }));"
      )
    ).toHaveLength(1);
    // 正常的跨页跳转不能被误伤（本页 askAbout 的写法）
    expect(
      inPlaceQueryCalls(
        'router.push({ name: "AgentChat", query: agentAskQuery({ from: "inventory" }) });'
      )
    ).toEqual([]);
  });

  it("`?tab=` 的**入站**寻址必须保留（只删写回，不删读取）", () => {
    expect(pageSource).toContain("route.query.tab");
  });
});

describe("资产明细表列口径（资产，不是产品）", () => {
  it("两张资产表用「资产名称」，不再叫「产品信息」", () => {
    for (const src of [categoryTable, otherTable]) {
      expect(src).toContain('label="资产名称"');
      expect(src).not.toContain('label="产品信息"');
    }
  });

  it("资产行不渲染无意义的 `# --` 代码占位", () => {
    // AssetRecord / 后端 AssetOut 都没有 symbol 字段
    expect(categoryTable).not.toContain(":symbol=");
    expect(otherTable).not.toContain(":symbol=");
  });
});

describe("操作列一行排版（防「删除」被挤到第二行）", () => {
  it("两个组件的行内操作都挂共享样式类", () => {
    expect(categoryTable).toContain('class="table-row-actions"');
    expect(otherTable).toContain('class="table-row-actions"');
  });

  it("共享类真的是「一行 + 不换行 + 清掉相邻按钮的 12px 左边距」", () => {
    const block = tableBaseline.match(
      /\.table-row-actions \{([\s\S]*?)\}/
    )?.[1];
    expect(block).toBeTruthy();
    expect(block).toContain("white-space: nowrap");
    expect(block).toContain("display: flex");
    expect(tableBaseline).toMatch(
      /\.table-row-actions \.el-button \+ \.el-button \{[^}]*margin-left: 0/
    );
  });
});
