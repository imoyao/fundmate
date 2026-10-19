import { describe, expect, it } from "vitest";
import { normalizeDomain } from "../domainQuery";

describe("normalizeDomain（URL query → 合法域标识，#2151）", () => {
  it("五个合法域原样返回", () => {
    expect(normalizeDomain("A")).toBe("A");
    expect(normalizeDomain("B")).toBe("B");
    expect(normalizeDomain("C")).toBe("C");
    expect(normalizeDomain("D")).toBe("D");
    expect(normalizeDomain("E")).toBe("E");
  });

  it("缺失 / 空串返回 null（回落策略交给调用方）", () => {
    expect(normalizeDomain(undefined)).toBeNull();
    expect(normalizeDomain(null)).toBeNull();
    expect(normalizeDomain("")).toBeNull();
  });

  it("非法值返回 null，不猜测、不回落", () => {
    expect(normalizeDomain("F")).toBeNull(); // 域 E 已接入后，F 才是「不存在的域」
    expect(normalizeDomain("e")).toBeNull(); // 大小写敏感：域标识是内部枚举值
    expect(normalizeDomain(" A ")).toBeNull();
    expect(normalizeDomain(1)).toBeNull();
  });

  it("重复参数（数组）取第一个：?domain=D&domain=A → D", () => {
    expect(normalizeDomain(["D", "A"])).toBe("D");
    expect(normalizeDomain(["X", "D"])).toBeNull(); // 首值非法即非法，不回落到数组里的合法值
  });
});
