/**
 * 复盘页口径能力表与接线守卫（#3287 B）。
 *
 * 四类失败模式，前三类各一条判据、第四类见文末「消费守卫」：
 *
 * 1. **档位开放超过实际能力** ⇒ 不支持的区块拿 `undefined` 当 props，面板侧把 `{}`
 *    读成家庭级 ⇒ 「组合」标签下摆着全家庭的钱。判据：`commonAnalysisKinds` 只回交集。
 * 2. **新增区块忘了登记** ⇒ 它的能力不进交集，档位照旧全开。判据：表内 label 集合
 *    必须与页面 `NAV_LABELS` 的值集合相等（加区块必然先加导航项）。
 * 3. **新增区块忘了接口径** ⇒ 切到账户 / 组合档，它自己还是家庭级数。
 *    判据：页面里 10 个区块的开标签逐个含 `v-bind="scopeProps"`（2026-11-28 起
 *    口径一次性下发；此前是逐个 `:ledger-id`，每加一档都是十处改动，漏一处
 *    就退回「静默错口径」）。
 *
 * 判据纪律（AGENTS「正则/字符串类判据」）：断言的是**完整子串**而非裸标识符，
 * 避免「文件里别处出现 scopeProps 就算过」的假阳性。
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
  it("三档全开：十块都支持组合档（D134 补 /positions/ 等 3 处、D135 补净值曲线）", () => {
    // 这条断言就是「档位 = 能力表交集」的最后一道确认：任何一块退回两档，
    // 交集立刻掉成 ["family", "ledger"]，组合档在页面上消失。
    expect(commonAnalysisKinds()).toEqual(["family", "ledger", "portfolio"]);
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

describe("接线守卫：10 个区块都必须收口径", () => {
  // 收益日历与收益归因是面板直连（面板自带 SectionHeader，页面只挂锚点），
  // 故这里匹配的是面板标签而不是包裹元素——匹配 `<section id="nav-…">` 会漏掉
  // 真正的取数入参。
  const SECTION_TAGS =
    /<(ReturnOverviewSection|ExcessSection|NetWorthTrendSection|CashFlowPanel|PnlCalendar|ClearedCyclesSection|BreakEvenSection|AnalysisStructureSection|PnlAttribution|MoneyFundIncomeSection)\b[^>]*>/g;

  it("页面恰好渲染 10 个区块（与能力表条目数一致）", () => {
    const tags = page.match(SECTION_TAGS) ?? [];
    expect(tags.length).toBe(Object.keys(ANALYSIS_SECTION_SCOPE).length);
  });

  it("每个区块的开标签都 v-bind scopeProps（漏一个就是静默错口径）", () => {
    const tags = page.match(SECTION_TAGS) ?? [];
    for (const tag of tags) {
      const name = tag.match(/^<(\w+)/)?.[1] ?? tag;
      expect(tag, `${name} 漏传 v-bind="scopeProps"`).toContain(
        'v-bind="scopeProps"'
      );
    }
  });

  it("页面不再逐块写 :ledger-id（组合档下会把组合 id 当账户 id 发出去）", () => {
    // 半迁移态最危险：`v-bind` 都加了，某块又留着 `:ledger-id="scopeId"`。
    // 切到组合档时它会把**组合 id** 当账户 id 发下去，后端要么 400、要么
    // 命中另一个账户 —— 数字错得毫无痕迹。故整页禁止出现逐块绑定。
    const tags = page.match(SECTION_TAGS) ?? [];
    for (const tag of tags) {
      const name = tag.match(/^<(\w+)/)?.[1] ?? tag;
      expect(tag, `${name} 还留着逐块 :ledger-id`).not.toContain(":ledger-id");
    }
  });

  it("资金流动的 family 必须跟着口径走，不能写死", () => {
    // 写死 `family` 会让账户档也报「本家庭」，卡面 4 张卡全错
    expect(page).toContain(":family=\"scopeKind === 'family'\"");
  });

  it("切换器两份清单分开喂（合成一份喂给 :ledgers ⇒ 组合档下拉恒空）", () => {
    // `ScopeBar` 内部按档位在 `ledgers` / `portfolios` 之间挑。若宿主把「按档位
    // 切过一遍」的单份清单喂进 `:ledgers`，组合档读到的是没被赋值的 `portfolios`
    // ⇒ 下拉永远是空的，并显示「暂无组合」——看起来像没有数据，实际是接线错。
    const bar = page.match(/<ScopeBar\b[\s\S]*?\/>/);
    expect(bar, "页面未渲染 ScopeBar").not.toBeNull();
    const tag = bar?.[0] ?? "";
    expect(tag).toContain(':ledgers="ledgerOptions"');
    expect(tag).toContain(':portfolios="portfolioOptions"');
  });
});

/**
 * 「声明了 prop」≠「真的按它取数」（第 4 类失败模式）。
 *
 * `v-bind="scopeProps"` 只保证 `portfolioId` **落到**十个区块上。若某块在
 * `defineProps` 里写了这个字段、却没把它拼进请求参数，页面照常渲染、`vue-tsc`
 * 照常通过、上面两条守卫也照常通过——唯一的现象是「组合标签下摆着更宽口径的钱」。
 * 这正是 #2595 的形态，也正是本次改造要消灭的东西，所以补一条「真消费」判据。
 *
 * 判据：**剥掉注释后**，区块源及其数据层（composable / 子面板）里必须出现
 * `portfolio_id`（接口参数名）。两处刻意设计：
 *
 * - 要的是 snake_case 的**接口参数**，不是 camelCase 的 prop 名：只有 prop 声明
 *   时这个字符串根本不出现，正好防住「声明了不用」。
 * - 必须先剥注释：说明文字里写一句 `portfolioId` 就能喂出假绿，本仓有过教训。
 *
 * 唯一例外是收益概览：`getPortfolioXirr` 的位置参数签名（`portfolioId` 是第 2 个
 * 位置参数），请求参数不是对象字面量，故那个区块的凭据是 `props.portfolioId`
 * 作为实参出现——同样是「值真的进了请求」，只是编码方式不同。
 *
 * 表里每个 key 必须与能力表一一对应（下面第一条断言钉住），新增区块忘了登记时
 * 会直接红在「缺消费证据」上，而不是等用户看见错数。
 */
interface ScopeEvidence {
  /** 该区块口径真正变成请求参数的地方（区块自身 + 它的数据层） */
  files: string[];
  /** 剥注释后必须出现的凭据 */
  evidence: string;
}

const SECTION_SOURCES: Record<string, ScopeEvidence> = {
  overview: {
    files: ["../ReturnOverviewSection.vue"],
    // 位置参数调用，没有 portfolio_id 字样
    evidence: "props.portfolioId"
  },
  excess: { files: ["../ExcessSection.vue"], evidence: "portfolio_id" },
  // 净值：区块只管渲染，参数在 composable 里拼
  netWorth: {
    files: [
      "../NetWorthTrendSection.vue",
      "../composables/useNetWorthTrend.ts"
    ],
    evidence: "portfolio_id"
  },
  // 资金流动：参数构造已下沉成纯函数 `cashFlowParams`（有独立单测）
  cashFlow: {
    files: [
      "../../../components/CashFlowPanel/index.vue",
      "../../../components/CashFlowPanel/cashFlowParams.ts"
    ],
    evidence: "portfolio_id"
  },
  calendar: {
    files: [
      "../../../components/PnlCalendar/index.vue",
      "../../../components/PnlCalendar/usePnlCalendarData.ts"
    ],
    evidence: "portfolio_id"
  },
  cycles: {
    files: ["../cleared-cycles/ClearedCyclesSection.vue"],
    evidence: "portfolio_id"
  },
  breakEven: { files: ["../BreakEvenSection.vue"], evidence: "portfolio_id" },
  // 结构区：三块面板各自取数，区块只做口径透传
  structure: {
    files: [
      "../AnalysisStructureSection.vue",
      "../../../components/PositionStructurePanel/index.vue",
      "../../../components/PenetrationPanel/index.vue",
      "../../../components/StyleDistributionCard/index.vue"
    ],
    evidence: "portfolio_id"
  },
  attribution: {
    files: ["../../../components/PnlAttribution/index.vue"],
    evidence: "portfolio_id"
  },
  moneyFund: {
    files: ["../MoneyFundIncomeSection.vue"],
    evidence: "portfolio_id"
  }
};

describe("消费守卫：每个区块真的按 portfolioId 取数", () => {
  /** 剥 HTML 注释 / 块注释 / 整行 `//`，注释里提一句不算消费 */
  const stripComments = (src: string) =>
    src
      .replace(/<!--[\s\S]*?-->/g, "")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");

  it("登记表覆盖能力表的每一个区块（新增区块必须同时给出消费证据）", () => {
    expect(Object.keys(SECTION_SOURCES).sort()).toEqual(
      Object.keys(ANALYSIS_SECTION_SCOPE).sort()
    );
  });

  it("每个区块的链路里都带着组合 id（只有 prop 声明 = 静默错口径）", () => {
    for (const [key, { files, evidence }] of Object.entries(SECTION_SOURCES)) {
      const src = stripComments(files.map(f => read(f)).join("\n"));
      expect(src, `${key} 没把 portfolioId 拼进请求参数`).toContain(evidence);
    }
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
