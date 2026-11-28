/**
 * 复盘页口径能力表与接线守卫（#3287 B）。
 *
 * 三类失败模式，各自一条判据：
 *
 * 1. **档位开放超过实际能力** ⇒ 不支持的区块拿 `undefined` 当 props，面板侧把 `{}`
 *    读成家庭级 ⇒ 「组合」标签下摆着全家庭的钱。判据：`commonAnalysisKinds` 只回交集。
 * 2. **新增区块忘了登记** ⇒ 它的能力不进交集，档位照旧全开。判据：表内 label 集合
 *    必须与页面 `NAV_LABELS` 的值集合相等（加区块必然先加导航项）。
 * 3. **新增区块忘了传 `:ledger-id`** ⇒ 切到账户档，它自己还是家庭级数。
 *    判据：页面里 10 个区块的开标签逐个含 `:ledger-id`。
 *
 * 判据纪律（AGENTS「正则/字符串类判据」）：断言的是**完整子串**而非裸标识符，
 * 避免「文件里别处出现 ledger-id 就算过」的假阳性。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  ANALYSIS_SECTION_SCOPE,
  commonAnalysisKinds,
  type SectionScope
} from "../analysisScopeSupport";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const page = read("../IntelligentAnalysis.vue");

describe("口径能力表（analysisScopeSupport）", () => {
  it("当前只开家庭 / 账户两档（组合档有 4 个后端空洞，按 D1 留到三期）", () => {
    expect(commonAnalysisKinds()).toEqual(["family", "ledger"]);
  });

  it("交集是逐档判定的：任一块不支持就不开该档", () => {
    const fake: Record<string, SectionScope> = {
      a: { label: "甲", kinds: ["family", "ledger", "portfolio"] },
      b: { label: "乙", kinds: ["family", "ledger"] }
    };
    expect(commonAnalysisKinds(fake)).toEqual(["family", "ledger"]);

    const allThree: Record<string, SectionScope> = {
      a: { label: "甲", kinds: ["family", "ledger", "portfolio"] }
    };
    expect(commonAnalysisKinds(allThree)).toEqual([
      "family",
      "ledger",
      "portfolio"
    ]);
  });

  it("空表回 ['family']：宁可只剩一档，也不摆出会取错数的档位", () => {
    expect(commonAnalysisKinds({})).toEqual(["family"]);
  });

  it("每个区块都必须支持家庭级（默认态不能是「未选对象」）", () => {
    for (const [key, s] of Object.entries(ANALYSIS_SECTION_SCOPE)) {
      expect(s.kinds, `${key} 缺 family 档`).toContain("family");
      expect(s.kinds.length, `${key} 的档位声明为空`).toBeGreaterThan(0);
    }
  });

  it("表内条目标签 == 页面导航项（加区块必然先加导航，故这条能拦住漏登记）", () => {
    // 页面里 NAV_LABELS 的值就是 rail / 胶囊上的文字
    const navBlock = page.match(/const NAV_LABELS[\s\S]*?\n\};/);
    expect(navBlock, "页面未找到 NAV_LABELS").not.toBeNull();
    const navLabels = [...(navBlock?.[0].match(/:\s*"([^"]+)"/g) ?? [])].map(
      m => m.replace(/^:\s*"/, "").replace(/"$/, "")
    );

    const tableLabels = Object.values(ANALYSIS_SECTION_SCOPE).map(s => s.label);
    expect(tableLabels.sort()).toEqual(navLabels.sort());
  });
});

describe("接线守卫：10 个区块都必须收 :ledger-id", () => {
  // 收益日历与收益归因是面板直连（面板自带 SectionHeader，页面只挂锚点），
  // 故这里匹配的是面板标签而不是包裹元素——匹配 `<section id="nav-…">` 会漏掉
  // 真正的取数入参。
  const SECTION_TAGS =
    /<(ReturnOverviewSection|ExcessSection|NetWorthTrendSection|CashFlowPanel|PnlCalendar|ClearedCyclesSection|BreakEvenSection|AnalysisStructureSection|PnlAttribution|MoneyFundIncomeSection)\b[^>]*>/g;

  it("页面恰好渲染 10 个区块（与能力表条目数一致）", () => {
    const tags = page.match(SECTION_TAGS) ?? [];
    expect(tags.length).toBe(Object.keys(ANALYSIS_SECTION_SCOPE).length);
  });

  it("每个区块的开标签都带 :ledger-id（漏一个就是静默错口径）", () => {
    const tags = page.match(SECTION_TAGS) ?? [];
    for (const tag of tags) {
      const name = tag.match(/^<(\w+)/)?.[1] ?? tag;
      expect(tag, `${name} 漏传 :ledger-id`).toContain(":ledger-id");
    }
  });

  it("资金流动的 family 必须跟着口径走，不能写死", () => {
    // 写死 `family` 会让账户档也报「本家庭」，卡面 4 张卡全错
    expect(page).toContain(":family=\"scopeKind === 'family'\"");
  });
});

/**
 * 懒加载接线守卫（2026-11-28，C2）。
 *
 * ## 被守的是什么
 *
 * `usePageNav` 的导航项来自**扫 DOM 里真实存在的 `nav-` 锚点**。`LazySection`
 * 的做法是「锚点 section 常驻、内容懒挂」——只要有人图省事把锚点也挪进懒挂的
 * 内容里，未挂载的区块就没有锚点，右侧目录直接少几项、scroll-spy 也认不出它们。
 * 这个退化在类型检查、lint、单测里全都不报，只有滚动到那里才看得见。
 *
 * ## 三条判据
 *
 * 1. **锚点集合 == 导航标签集合**：锚点写在哪都行（页面 tag 上 / 子组件根上 /
 *    `anchor-id`），但一个都不能少、也不能多。
 * 2. **同一个 id 只出现一次**：`LazySection` 的 anchor-id 与子组件里写死的 id
 *    同时存在时，`querySelectorAll` 会扫到两次 ⇒ 导航里这一项出现两遍。
 * 3. **懒加载区块必须给 min-height**：占位高度是「下方锚点位置」的唯一依据，
 *    缺省成 0 会让整页塌缩、rail 高亮错位到所有区块被激活为止。
 *
 * 判据一律先剥 HTML 注释：注释里提到某个 id 不该算作声明（本仓有过「注释喂
 * 假绿 / 假红」的教训）。
 */
describe("懒加载接线：锚点常驻，内容懒挂", () => {
  /** 剥 HTML 注释后再断言：注释里提到 id 不算声明 */
  const stripComments = (src: string) => src.replace(/<!--[\s\S]*?-->/g, "");

  /** `id="nav-x"` 与 `anchor-id="nav-x"` 都会被这个正则命中（后者尾部含 `id="`） */
  const navIdsOf = (src: string) =>
    [...stripComments(src).matchAll(/id="(nav-[^"]+)"/g)].map(m => m[1]);

  const pageIds = navIdsOf(page);

  /** 页面模板**不传** id、锚点由区块自己声明在根元素上的三块 */
  const ANCHOR_OWNED_SECTIONS = [
    "../ExcessSection.vue",
    "../BreakEvenSection.vue",
    "../MoneyFundIncomeSection.vue"
  ];
  const childIds = ANCHOR_OWNED_SECTIONS.flatMap(f => navIdsOf(read(f)));

  /** 被 LazySection 包住的区块：锚点必须在包裹层，不能同时留在它们根上 */
  const LAZY_CHILDREN = [
    "../AnalysisStructureSection.vue",
    "../cleared-cycles/ClearedCyclesSection.vue",
    "../../../components/CashFlowPanel/index.vue",
    "../../../components/PnlCalendar/index.vue",
    "../../../components/PnlAttribution/index.vue"
  ];

  const lazyAnchors = [
    ...stripComments(page).matchAll(/<LazySection[^>]*\banchor-id="([^"]+)"/g)
  ].map(m => m[1]);

  it("锚点集合与导航标签集合严格相等（少一个 = 导航缺项，多一个 = 死链）", () => {
    const navBlock = page.match(/const NAV_LABELS[\s\S]*?\n\};/);
    expect(navBlock, "页面未找到 NAV_LABELS").not.toBeNull();
    const labelIds = [
      ...(navBlock?.[0].matchAll(/"(nav-[\w-]+)":/g) ?? [])
    ].map(m => m[1]);

    expect([...pageIds, ...childIds].sort()).toEqual([...labelIds].sort());
  });

  it("同一个锚点 id 只声明一次（重复 ⇒ 导航里这一项出现两遍）", () => {
    // 只在**各自集合内**去重：页面传 `id` + 组件根也写 `id` 是合法的——Vue 的
    // attribute fallthrough 把它们合到同一个元素上，DOM 里只有一个 id
    //（`NetWorthTrendSection` 就是这种写法）。真正会渲染成两层节点的重复，
    // 由下面「被懒挂的区块不再自带同名锚点」那条钉死。
    for (const [label, ids] of [
      ["页面模板", pageIds],
      ["子组件根", childIds]
    ] as const) {
      const dup = ids.filter((id, i) => ids.indexOf(id) !== i);
      expect(dup, `${label}里重复声明的锚点：${dup.join(", ")}`).toEqual([]);
    }
  });

  it("每个 LazySection 都带 :min-height（占位塌陷会让 rail 高亮错位）", () => {
    const tags = page.match(/<LazySection\b[^>]*>/g) ?? [];
    expect(tags.length, "页面里没有 LazySection").toBeGreaterThan(0);
    for (const tag of tags) {
      const anchor = tag.match(/anchor-id="([^"]+)"/)?.[1] ?? tag;
      expect(tag, `${anchor} 缺 :min-height`).toMatch(/:min-height="\d+"/);
    }
  });

  it("被懒挂的区块不再自带同名锚点（锚点归包裹层唯一所有）", () => {
    const childSrc = stripComments(LAZY_CHILDREN.map(f => read(f)).join("\n"));
    for (const anchor of lazyAnchors) {
      expect(childSrc, `子组件里不该再有 id="${anchor}"`).not.toContain(
        `id="${anchor}"`
      );
    }
    // 反向：LazySection 的锚点必须真的出现在页面锚点集合里
    for (const anchor of lazyAnchors) {
      expect(pageIds).toContain(anchor);
    }
  });
});
