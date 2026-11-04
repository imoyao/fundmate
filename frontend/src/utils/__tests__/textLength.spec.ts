import { describe, expect, it } from "vitest";
import { textLength } from "../textLength";

describe("textLength", () => {
  it("空值与空串返回 0", () => {
    expect(textLength("")).toBe(0);
    expect(textLength(null)).toBe(0);
    expect(textLength(undefined)).toBe(0);
  });

  it("BMP 内中文每字算 1（与 .length 一致）", () => {
    expect(textLength("阿宝")).toBe(2);
    expect(textLength("abc")).toBe(3);
  });

  it("增补平面 emoji 算 1（原生 .length 会算 2，口径分叉点）", () => {
    expect("😀".length).toBe(2); // 对照：UTF-16 code unit 口径
    expect(textLength("😀")).toBe(1); // 码点口径，与后端 len() 一致
  });

  it("组合 emoji 按 ZWJ 序列的码点数计（👨‍👩‍👧 = 5 码点，非 1 字素）", () => {
    // U+1F468 + U+200D + U+1F469 + U+200D + U+1F467 = 5 码点
    expect("👨‍👩‍👧".length).toBe(8); // 对照：UTF-16（3 emoji×2 + 2 ZWJ×1）
    expect(textLength("👨‍👩‍👧")).toBe(5);
  });

  it("混合字符串（中文 + emoji + 拉丁）", () => {
    expect(textLength("朵😀a")).toBe(3);
  });
});
