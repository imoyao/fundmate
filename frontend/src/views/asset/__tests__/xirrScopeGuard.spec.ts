/**
 * XIRR 口径一致性守卫（#2153 回归网）：
 *
 * 1. **调用点必须显式传口径**——投资概览（useWelcomeData）与智能分析
 *    （IntelligentAnalysis）调 getPortfolioXirr 时都要带 includeCashEquivalents。
 *    漏传的一侧会静默落回后端默认值，两页数值分叉且无提示（#2153 症状）；
 * 2. **默认口径统一为 ref(false)（剔除现金）**——与后端 include_cash_equivalents
 *    默认值一致，两页开箱数值一致；
 * 3. **开关文案逐字一致**——「剔除现金 / 含现金」同字面，对应验收
 *    「切换状态在两处语义一致、且用户可见」。
 *
 * 边界：组合详情页（portfolio/detail.vue）是 portfolio_id 级、scope 不同，
 * 不在本守卫范围（#2153 只约束投资概览与智能分析两页）。
 *
 * 判据纪律（AGENTS「正则/字符串类判据」）：
 * - 调用抽取用 `getPortfolioXirr\([^)]*\)`：实参内无嵌套括号，[^)]* 不会截错；
 * - 断言的是**完整子串**（含括号与参数名），不是裸标识符，避免「文件里别处
 *   出现 includeCashEquivalents 就算过」的假阳性。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const analysis = read("../IntelligentAnalysis.vue");
const welcomeData = read("../../welcome/composables/useWelcomeData.ts");
const welcomeUi = read("../../welcome/components/WelcomeXirrTemperature.vue");

/** 抽出文件内全部 getPortfolioXirr(…) 调用（含实参） */
const xirrCalls = (src: string) =>
  src.match(/getPortfolioXirr\([^)]*\)/g) ?? [];

describe("XIRR 口径一致性守卫（#2153）", () => {
  it("两页调用点都显式传 includeCashEquivalents（漏传 → 静默回退默认 → 数值分叉）", () => {
    const callSites = [
      ["智能分析 IntelligentAnalysis.vue", analysis],
      ["投资概览 useWelcomeData.ts", welcomeData]
    ] as const;
    for (const [name, src] of callSites) {
      const calls = xirrCalls(src);
      expect(
        calls.length,
        `${name} 应有 getPortfolioXirr 调用`
      ).toBeGreaterThan(0);
      for (const c of calls) {
        expect(c, `${name} 调用漏传口径：${c.replace(/\s+/g, " ")}`).toContain(
          "includeCashEquivalents"
        );
      }
    }
  });

  it("默认口径统一为 ref(false)（= 后端默认「剔除现金」，两页开箱一致）", () => {
    const decl = "const includeCashEquivalents = ref(false)";
    expect(analysis, "智能分析缺本地口径状态").toContain(decl);
    expect(welcomeData, "投资概览缺本地口径状态").toContain(decl);
  });

  it("开关文案逐字一致（验收：切换状态在两处语义一致、且用户可见）", () => {
    const radioOff =
      '<el-radio-button :value="false">剔除现金</el-radio-button>';
    const radioOn = '<el-radio-button :value="true">含现金</el-radio-button>';
    for (const [name, src] of [
      ["智能分析", analysis],
      ["投资概览", welcomeUi]
    ] as const) {
      expect(src, `${name} 缺「剔除现金」选项`).toContain(radioOff);
      expect(src, `${name} 缺「含现金」选项`).toContain(radioOn);
    }
  });
});
