/**
 * tooltip 载体判据（2026-11-02 截图反馈：一条 110 字的口径说明被铺成一整行）。
 *
 * 这些判据以前根本不存在——提示文案一律走默认深色气泡，长度是多少就铺多宽。判据现在
 * 决定「深色短语 / 浅色说明卡」与「按句分行」，写错了不会报错，只会把一段说明又变回
 * 一根横条，所以逐条钉住。
 */
import { describe, expect, it } from "vitest";
import {
  isRichTipText,
  RICH_TIP_MIN_CHARS,
  splitTipSentences,
  tipParagraphs,
  tipPopperClass
} from "../tooltipText";

/** 截图里那条「收益概览」的真实运行时文案（XIRR + 不含现金等价物） */
const XIRR_SCOPE_INFO =
  "由已录入的交易现金流真实计算，录入交易后自动生成；本页不做收益预测。" +
  "当前口径：基于主动投资交易，不含货币基金等现金等价物。" +
  "XIRR：资金加权年化，反映个人持有体验，受申赎时点影响。";

describe("isRichTipText", () => {
  it("短短语仍走深色气泡", () => {
    expect(
      isRichTipText("来源：通用资产记录（大类贵金属 / 固定资产·黄金）")
    ).toBe(false);
    expect(
      isRichTipText(
        "设定期望的年化股息率，用于对照组合实际的「分红 / 成本」回报"
      )
    ).toBe(false);
  });

  it("阈值本身仍是短语气泡，多一个字才升格", () => {
    expect(isRichTipText("字".repeat(RICH_TIP_MIN_CHARS))).toBe(false);
    expect(isRichTipText("字".repeat(RICH_TIP_MIN_CHARS + 1))).toBe(true);
  });

  it("截图里那条口径说明要升格成说明卡", () => {
    expect(isRichTipText(XIRR_SCOPE_INFO)).toBe(true);
  });

  it("空白字符不参与计长（首尾换行不该把短文案顶过线）", () => {
    expect(isRichTipText(`   ${"字".repeat(RICH_TIP_MIN_CHARS)}   `)).toBe(
      false
    );
    expect(isRichTipText("")).toBe(false);
    expect(isRichTipText("   ")).toBe(false);
  });

  it("动态文案按**渲染后**的字数判：短的不该被源码里的表达式长度顶成卡片", () => {
    // 源码写作 `'共 ' + list.length + ' 条，可在对账中心逐条决策'`，实渲染约 20 字
    expect(isRichTipText("共 3 条，可在对账中心逐条决策")).toBe(false);
  });
});

describe("splitTipSentences", () => {
  it("一句一行，句号留在句尾", () => {
    expect(splitTipSentences("第一句。第二句。")).toEqual([
      "第一句。",
      "第二句。"
    ]);
  });

  it("末句没有句号也不丢（口径说明常这么结尾）", () => {
    expect(splitTipSentences("第一句。第二句没有句号")).toEqual([
      "第一句。",
      "第二句没有句号"
    ]);
  });

  it("括号 / 引号内的句号不切", () => {
    // 括号内是独立句子，切开会把「（比如这样。」变成一个开口的残句
    expect(
      splitTipSentences("括号内不切（比如这样。还有内容）。第二句。")
    ).toEqual(["括号内不切（比如这样。还有内容）。", "第二句。"]);
    expect(splitTipSentences("书名里也有（《上。下》）句号。第二句。")).toEqual(
      ["书名里也有（《上。下》）句号。", "第二句。"]
    );
  });

  it("多写一个右括号不会让后面的句子永远不切", () => {
    // 深度用 Math.max(0, …) 兜底：文案笔误不该把整段锁成一句
    expect(splitTipSentences("多一个右括号）】。第二句。")).toEqual([
      "多一个右括号）】。",
      "第二句。"
    ]);
  });

  it("没有句号 ⇒ 整段一句（说明卡里就是一段话）", () => {
    const one =
      "按「万份收益 × 持有份额」估算，与上方 XIRR 口径不同（XIRR 衡量交易现金流的时间价值），两者不可相加；本项已计入总资产";
    expect(splitTipSentences(one)).toEqual([one]);
  });

  it("连写的两个句号并回上一段，不单独占一行", () => {
    // 单独成段会被 <p> 的段间距撑出一个空行，且「一个字都不丢」
    expect(splitTipSentences("第一句。。第三句。")).toEqual([
      "第一句。。",
      "第三句。"
    ]);
  });
});

describe("tipParagraphs", () => {
  it("短文案不产生段落（仍走深色气泡，不该多包一层 <p>）", () => {
    expect(tipParagraphs("共 3 条，可在对账中心逐条决策")).toEqual([]);
  });

  it("收益概览的口径说明切成三段，每段是一句", () => {
    expect(tipParagraphs(XIRR_SCOPE_INFO)).toEqual([
      "由已录入的交易现金流真实计算，录入交易后自动生成；本页不做收益预测。",
      "当前口径：基于主动投资交易，不含货币基金等现金等价物。",
      "XIRR：资金加权年化，反映个人持有体验，受申赎时点影响。"
    ]);
  });

  it("拼接后的段落合起来等于原文（分行不吞字）", () => {
    expect(tipParagraphs(XIRR_SCOPE_INFO).join("")).toBe(
      XIRR_SCOPE_INFO.trim()
    );
  });
});

describe("tipPopperClass", () => {
  it("短文案 ⇒ 空串，走 Element Plus 默认深色气泡", () => {
    expect(tipPopperClass("共 3 条，可在对账中心逐条决策")).toBe("");
  });

  it("长文案 ⇒ 卡片 + 段落修饰，两个载体取同一份，免得一处忘了挂", () => {
    expect(tipPopperClass(XIRR_SCOPE_INFO)).toBe(
      "rich-tip rich-tip--paragraphs"
    );
  });
});
