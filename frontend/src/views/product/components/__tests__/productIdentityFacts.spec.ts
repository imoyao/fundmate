/**
 * 识别卡「代码」项可见性（#2228）。
 *
 * 复核结论是「**设计写了、代码没落地**」：设计 §2.6 明确「组合 / 经理类不展示代码」，
 * 而 `ProductIdentityCard` 里那行是无条件渲染的 —— 于是经理详情页把
 * `MGR_98CE0328FFF1` 这种内部编码摆给用户看。这类「设计已定、实现漏掉」的口径
 * 最容易回潮，所以钉在纯函数上。
 */
import { describe, it, expect } from "vitest";
import {
  NO_CODE_ASSET_TYPES,
  hasIdentityFacts,
  showsCodeItem
} from "../productIdentityFacts";

describe("showsCodeItem：哪些品类不展示「代码」", () => {
  it("经理 / 组合 → 不展示（symbol 是内部编码）", () => {
    expect(showsCodeItem("manager")).toBe(false);
    expect(showsCodeItem("portfolio")).toBe(false);
  });

  it("可交易 / 可查看品类照常展示", () => {
    for (const t of [
      "fund",
      "money_fund",
      "stock",
      "etf",
      "bond",
      "convertible_bond",
      "index"
    ]) {
      expect(showsCodeItem(t)).toBe(true);
    }
  });

  it("asset_type 缺失 → 展示（「不知道品类」不该变成隐藏信息）", () => {
    expect(showsCodeItem(undefined)).toBe(true);
    expect(showsCodeItem(null)).toBe(true);
    expect(showsCodeItem("")).toBe(true);
    expect(showsCodeItem("   ")).toBe(true);
  });

  it("大小写 / 空白归一后再判（不把健壮性押在调用方身上）", () => {
    expect(showsCodeItem("MANAGER")).toBe(false);
    expect(showsCodeItem(" manager ")).toBe(false);
    expect(showsCodeItem("Portfolio")).toBe(false);
  });

  it("口径清单本身不可为空（防止有人「顺手」清空它让代码项全回来）", () => {
    expect([...NO_CODE_ASSET_TYPES]).toEqual(["manager", "portfolio"]);
  });
});

/**
 * 识别卡**是否成卡**（2026-11-26）。
 *
 * 旧判据是「有任何一项就成卡」，把状态（自选 / 持仓）也算成了内容 —— 于是组合 /
 * 经理类在用户自选之后，会得到一张横贯整行、只写「自选 / 已关注」的横幅卡：
 * 不可操作、不携带事实。用户实测原话：「这个自选直接一个横幅卡片，而且似乎也
 * 没有什么意义……没办法取消自选，没办法显示 tag。」
 */
describe("hasIdentityFacts：身份事实才成卡（状态不算）", () => {
  it("组合 / 经理类：无身份事实 → 不成卡（即使已自选 / 已持有）", () => {
    // 状态字段根本不参与判定，传不传都一样 —— 这正是判据收窄的意义
    expect(
      hasIdentityFacts({ asset_type: "portfolio", market: null, venue: null })
    ).toBe(false);
    expect(hasIdentityFacts({ asset_type: "manager" })).toBe(false);
  });

  it("基金 / 股票等有代码项 → 成卡", () => {
    expect(hasIdentityFacts({ asset_type: "fund" })).toBe(true);
    expect(hasIdentityFacts({ asset_type: "stock" })).toBe(true);
    expect(hasIdentityFacts({ asset_type: "etf" })).toBe(true);
  });

  it("品类缺失但有市场 / 场所 → 成卡（有身份事实就别丢卡）", () => {
    expect(hasIdentityFacts({ asset_type: null, market: "CN_A" })).toBe(true);
    expect(hasIdentityFacts({ asset_type: null, venue: "EXCHANGE" })).toBe(
      true
    );
  });

  it("组合类三者全空 → 不成卡（不造空白壳）", () => {
    // 注意：`asset_type` 缺失**不算全空**——按既有口径「不知道品类就展示代码」，
    // 那种情况本来就成卡（见上一条）。这里必须是「明确是组合 + 无市场 / 场所」。
    expect(
      hasIdentityFacts({
        asset_type: "portfolio",
        market: "",
        venue: undefined
      })
    ).toBe(false);
    expect(
      hasIdentityFacts({ asset_type: "manager", market: null, venue: null })
    ).toBe(false);
  });

  it("判据非空转：无市场 / 场所时，成卡与否完全由代码项决定", () => {
    // 不变式本身可被证伪——若有人把 hasIdentityFacts 写死 true，
    // portfolio / manager 两条立刻红，而不是「碰巧绿」
    for (const t of ["portfolio", "manager", "fund", "stock", undefined, ""]) {
      expect(hasIdentityFacts({ asset_type: t })).toBe(showsCodeItem(t));
    }
  });
});
