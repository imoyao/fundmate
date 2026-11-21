/**
 * 占比标注 `shareOfTotal` 的判据网。
 *
 * 重点不在「除法对不对」，而在**兜底分支**：占比不可计算时必须返回 null
 * 让调用方整项不渲染——返回 "0.0%" 会把「不知道」说成「没有」，
 * 这类静默把未知说成零的写法是本仓反复踩过的坑（当日盈亏的 `—` 同理）。
 */
import { describe, expect, it } from "vitest";
import { shareOfTotal } from "../overviewShare";

describe("shareOfTotal", () => {
  it("常规占比保留一位小数", () => {
    expect(shareOfTotal(282048, 3300962.73)).toBe("8.5%");
    expect(shareOfTotal(240000, 1000000)).toBe("24.0%");
  });

  it("零份额是真实的 0.0%，不是 null", () => {
    expect(shareOfTotal(0, 1000)).toBe("0.0%");
  });

  it("极小但非零给 0.1%：不与「一点没有」混为一谈", () => {
    expect(shareOfTotal(1, 100000)).toBe("0.1%");
  });

  it("分项大于整体时不写 >100%", () => {
    expect(shareOfTotal(1200, 1000)).toBe("100%");
    expect(shareOfTotal(1000, 1000)).toBe("100%");
  });

  it("不可计算一律 null（调用方整项不渲染）", () => {
    expect(shareOfTotal(null, 1000)).toBeNull();
    expect(shareOfTotal(undefined, 1000)).toBeNull();
    expect(shareOfTotal(Number.NaN, 1000)).toBeNull();
    expect(shareOfTotal(-1, 1000)).toBeNull();
    expect(shareOfTotal(100, 0)).toBeNull();
    expect(shareOfTotal(100, -5)).toBeNull();
    expect(shareOfTotal(100, Number.POSITIVE_INFINITY)).toBeNull();
  });
});
