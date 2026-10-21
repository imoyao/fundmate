/**
 * 「行业恐贪」展示口径测试（#2479 · 探市「行业情绪」档）。
 *
 * 重点钉住几个**静默错误**：
 * - 五档阈值边界（20/40/60/80）被取错档；
 * - null/NaN 被冒充成中性或错误档（「缺失」与「中性」是两件事）；
 * - 小数恐贪值被错误补尾零 / 整数被加 .0。
 */
import { describe, it, expect } from "vitest";
import type { IndustryEmotionItem } from "@/api/market";
import {
  emotionLevel,
  sortedEmotionItems,
  historyText,
  formatEmotionValue
} from "../industryEmotionMetrics";

describe("emotionLevel", () => {
  it("边界值分档正确（0-20 极端恐惧，80-100 极度贪婪）", () => {
    expect(emotionLevel(0).key).toBe("extreme-fear");
    expect(emotionLevel(19.9).key).toBe("extreme-fear");
    expect(emotionLevel(20).key).toBe("fear");
    expect(emotionLevel(39.9).key).toBe("fear");
    expect(emotionLevel(40).key).toBe("neutral");
    expect(emotionLevel(59.9).key).toBe("neutral");
    expect(emotionLevel(60).key).toBe("greed");
    expect(emotionLevel(79.9).key).toBe("greed");
    expect(emotionLevel(80).key).toBe("extreme-greed");
    expect(emotionLevel(100).key).toBe("extreme-greed");
  });

  it("null / NaN 回退中性，不冒充具体档", () => {
    expect(emotionLevel(null).key).toBe("neutral");
    expect(emotionLevel(Number.NaN).key).toBe("neutral");
  });
});

describe("sortedEmotionItems", () => {
  const make = (name: string, value: number | null): IndustryEmotionItem => ({
    name,
    industry: name,
    metric: null,
    value,
    history_days: 1
  });

  it("value 降序 = 自带排行", () => {
    const items = [make("a", 10), make("b", 99), make("c", 34)];
    const got = sortedEmotionItems(items).map(i => i.value);
    expect(got).toEqual([99, 34, 10]);
  });

  it("null 值防御性排最后（不抛、不排前）", () => {
    const items = [make("a", null), make("b", 50), make("c", null)];
    const got = sortedEmotionItems(items);
    expect(got[0].value).toBe(50);
    expect(got[1].value).toBeNull();
    expect(got[2].value).toBeNull();
  });

  it("不改动入参（纯函数）", () => {
    const items = [make("a", 10), make("b", 99)];
    sortedEmotionItems(items);
    expect(items.map(i => i.value)).toEqual([10, 99]);
  });
});

describe("historyText", () => {
  it("不足 2 天不显示（「1 天」无信息量）", () => {
    expect(historyText(0)).toBe("");
    expect(historyText(1)).toBe("");
  });

  it("≥2 天给出累积提示", () => {
    expect(historyText(2)).toBe("已累积 2 天历史");
    expect(historyText(12)).toBe("已累积 12 天历史");
  });
});

describe("formatEmotionValue", () => {
  it("整数不带小数", () => {
    expect(formatEmotionValue(34)).toBe("34");
    expect(formatEmotionValue(0)).toBe("0");
  });

  it("小数保留两位并去尾零", () => {
    expect(formatEmotionValue(99.85)).toBe("99.85");
    expect(formatEmotionValue(40.0)).toBe("40");
  });

  it("null / NaN 渲染「—」", () => {
    expect(formatEmotionValue(null)).toBe("—");
    expect(formatEmotionValue(Number.NaN)).toBe("—");
  });
});
