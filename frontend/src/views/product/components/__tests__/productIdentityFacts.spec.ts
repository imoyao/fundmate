/**
 * 识别卡「代码」项可见性（#2228）。
 *
 * 复核结论是「**设计写了、代码没落地**」：设计 §2.6 明确「组合 / 经理类不展示代码」，
 * 而 `ProductIdentityCard` 里那行是无条件渲染的 —— 于是经理详情页把
 * `MGR_98CE0328FFF1` 这种内部编码摆给用户看。这类「设计已定、实现漏掉」的口径
 * 最容易回潮，所以钉在纯函数上。
 */
import { describe, it, expect } from "vitest";
import { NO_CODE_ASSET_TYPES, showsCodeItem } from "../productIdentityFacts";

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
