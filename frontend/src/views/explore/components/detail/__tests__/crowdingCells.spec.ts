/**
 * 拥挤度表格的数字写法（#980 批 B5 拆出 `crowdingCells.ts` 时补的网）。
 *
 * 这三条规则决定「缺数据怎么说」与「0 怎么说」——两者在同一张表里紧挨着，
 * 混淆的代价是把「没取到数」读成「真的是 0」。`--` 与 `0.0%` / `0.0亿`
 * 在视觉上只差一个字符，肉眼极难发现写错。
 */
import { describe, expect, it } from "vitest";
import {
  BIAS_WINDOWS,
  bigOrderClass,
  bigOrderText,
  fmtPct
} from "../crowdingCells";

describe("fmtPct", () => {
  it("一位小数 + %", () => {
    expect(fmtPct(0)).toBe("0.0%");
    expect(fmtPct(52.34)).toBe("52.3%");
    expect(fmtPct(100)).toBe("100.0%");
  });

  it("null / undefined ⇒ 「--」，绝不补 0", () => {
    expect(fmtPct(null)).toBe("--");
    expect(fmtPct(undefined)).toBe("--");
  });

  it("0 是真实读数，不能与缺数据混为一谈", () => {
    expect(fmtPct(0)).not.toBe(fmtPct(null));
  });
});

describe("bigOrderClass", () => {
  it("净买入红、净卖出绿", () => {
    expect(bigOrderClass(1.2)).toBe("big-order--in");
    expect(bigOrderClass(-0.3)).toBe("big-order--out");
  });

  it("0 与缺数据都不着色（0 既不是买也不是卖）", () => {
    expect(bigOrderClass(0)).toBe("");
    expect(bigOrderClass(null)).toBe("");
    expect(bigOrderClass(undefined)).toBe("");
  });
});

describe("bigOrderText", () => {
  it("正数带 + 号、负数自带 -，统一一位小数 + 亿", () => {
    expect(bigOrderText(2.34)).toBe("+2.3亿");
    expect(bigOrderText(-1.25)).toBe("-1.3亿");
    expect(bigOrderText(0)).toBe("0.0亿");
  });

  it("缺数据 ⇒ 「--」，不显示 0.0 亿", () => {
    expect(bigOrderText(null)).toBe("--");
    expect(bigOrderText(undefined)).toBe("--");
  });
});

describe("BIAS_WINDOWS", () => {
  it("与后端 sw_industry_source.BIAS_WINDOWS 对齐（6 / 20 / 60）", () => {
    expect(BIAS_WINDOWS).toEqual([6, 20, 60]);
  });
});
