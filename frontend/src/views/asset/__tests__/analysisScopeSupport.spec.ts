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
