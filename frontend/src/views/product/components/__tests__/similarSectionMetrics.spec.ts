/**
 * 「相似基金」区块展示口径测试（#2480）。
 *
 * 重点钉两个**静默错误**：
 * - similarity=null 被 `?? 0` 冒充成 0 分（上游只给前若干名打分）；
 * - 正收益漏 `+` 号 / null 借用涨跌配色。
 */
import { describe, it, expect } from "vitest";
import {
  DASH,
  similarityText,
  similarityTitle,
  incomeText,
  incomeClass
} from "../similarSectionMetrics";

describe("similarityText", () => {
  it("null = 上游未打分，渲染「—」而非 0", () => {
    expect(similarityText(null)).toBe(DASH);
    expect(similarityText(undefined)).toBe(DASH);
  });

  it("0 分是有效打分，与 null 区分", () => {
    expect(similarityText(0)).toBe("0");
    expect(similarityText(97)).toBe("97");
  });
});

describe("similarityTitle", () => {
  it("null 的点提示「上游未打分」", () => {
    expect(similarityTitle(null)).toBe("上游未打分");
  });

  it("有分时给口径说明", () => {
    expect(similarityTitle(100)).toBe("相似度分（0-100）");
  });
});

describe("incomeText", () => {
  it("正数带 + 号", () => {
    expect(incomeText(8.33)).toBe("+8.33%");
  });

  it("负数自带 - 号，不叠加", () => {
    expect(incomeText(-7.39)).toBe("-7.39%");
  });

  it("0 不带符号", () => {
    expect(incomeText(0)).toBe("0.00%");
  });

  it("null 回「—」", () => {
    expect(incomeText(null)).toBe(DASH);
  });
});

describe("incomeClass", () => {
  it("涨红跌绿、null 中性", () => {
    expect(incomeClass(8.33)).toBe("rise");
    expect(incomeClass(-7.39)).toBe("fall");
    expect(incomeClass(null)).toBe("flat");
    expect(incomeClass(0)).toBe("flat");
  });
});
