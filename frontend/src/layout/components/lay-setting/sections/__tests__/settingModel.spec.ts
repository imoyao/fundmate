import { describe, expect, it } from "vitest";

import {
  NAV_MODE_OPTIONS,
  SECTION_TITLE_CLASS,
  isStretchNumber,
  markIndex,
  overallStyleIndex,
  showThemeColor,
  stretchIndex,
  stretchValueOf,
  themeColorMark
} from "../settingModel";

/**
 * 外观设置面板的纯函数层（#980 拆分）。
 *
 * 这些原本是模板里的三元表达式，改一处要肉眼对下标；这里把每条分支钉住：
 * 尤其 `overallStyleIndex` 的 `system` 优先级（它必须压过 `dataTheme`，否则
 * 「自动」档会被渲染成「深色」），以及 `stretchValueOf` 的 1440（落在
 * 1280–1600 区间内，改档后输入框不会立刻越界）。
 */

describe("overallStyleIndex", () => {
  it("system 档恒为 2，压过 dataTheme", () => {
    expect(overallStyleIndex("system", false)).toBe(2);
    expect(overallStyleIndex("system", true)).toBe(2);
  });

  it("非 system 档按 dataTheme 落 1（深）/ 0（浅）", () => {
    expect(overallStyleIndex("dark", true)).toBe(1);
    expect(overallStyleIndex("light", false)).toBe(0);
    // 值与档位不一致时以 dataTheme 为准（Segmented 只认下标）
    expect(overallStyleIndex("light", true)).toBe(1);
  });

  it("缺失 / undefined 视作浅色，不落空档", () => {
    expect(overallStyleIndex(undefined, undefined)).toBe(0);
    expect(overallStyleIndex(null, null)).toBe(0);
  });
});

describe("markIndex", () => {
  it("smart / card 各占一档，其余归到「谷歌」", () => {
    expect(markIndex("smart")).toBe(0);
    expect(markIndex("card")).toBe(1);
    expect(markIndex("chrome")).toBe(2);
  });

  it("未知值不落到前两档（历史脏数据不至于显示成灵动）", () => {
    expect(markIndex("")).toBe(2);
    expect(markIndex(undefined)).toBe(2);
  });
});

describe("页宽", () => {
  it("只有数字算「自定义」，false 与缺值都算固定", () => {
    expect(isStretchNumber(1440)).toBe(true);
    expect(isStretchNumber(false)).toBe(false);
    expect(isStretchNumber(undefined)).toBe(false);
  });

  it("NaN 不当数字（输入框清空时的中间态）", () => {
    expect(isStretchNumber(Number.NaN)).toBe(false);
    expect(stretchIndex(Number.NaN)).toBe(0);
  });

  it("下标：数字→1，其余→0", () => {
    expect(stretchIndex(1440)).toBe(1);
    expect(stretchIndex(false)).toBe(0);
  });

  it("档位→值：自定义落 1440（区间中位），固定落 false", () => {
    expect(stretchValueOf("custom")).toBe(1440);
    expect(stretchValueOf("fixed")).toBe(false);
    expect(stretchValueOf(undefined)).toBe(false);
  });

  it("1440 落在 1280–1600 的输入区间内（改档不会立刻越界）", () => {
    const v = stretchValueOf("custom");
    expect(v).toBeGreaterThanOrEqual(1280);
    expect(v).toBeLessThanOrEqual(1600);
  });
});

describe("themeColorMark", () => {
  it("未选中的色块不打勾", () => {
    expect(themeColorMark("default", "light")).toBe("transparent");
  });

  it("浅色主题上的勾用深蓝（白勾会看不见）", () => {
    expect(themeColorMark("light", "light")).toBe("#1d2b45");
  });

  it("深色系主题上的勾用白色", () => {
    expect(themeColorMark("default", "default")).toBe("#fff");
    expect(themeColorMark("showbuy", "showbuy")).toBe("#fff");
  });
});

describe("showThemeColor", () => {
  it("整体暗色时隐藏亮白色块（与深色块几乎同色）", () => {
    expect(showThemeColor("light", true)).toBe(false);
  });

  it("其余组合都展示", () => {
    expect(showThemeColor("light", false)).toBe(true);
    expect(showThemeColor("default", true)).toBe(true);
    expect(showThemeColor("default", false)).toBe(true);
  });
});

describe("NAV_MODE_OPTIONS", () => {
  it("顺序即渲染顺序：左侧在前，顶部 / 混合在窄屏下隐藏", () => {
    expect(NAV_MODE_OPTIONS.map(o => o.layout)).toEqual([
      "vertical",
      "horizontal",
      "mix"
    ]);
    expect(NAV_MODE_OPTIONS[0].mobileHidden).toBeFalsy();
    expect(NAV_MODE_OPTIONS[1].mobileHidden).toBe(true);
    expect(NAV_MODE_OPTIONS[2].mobileHidden).toBe(true);
  });

  it("每一项都有悬浮提示（原来写在模板的 v-tippy 里）", () => {
    for (const o of NAV_MODE_OPTIONS) {
      expect(o.tip).toBeTruthy();
    }
  });
});

describe("SECTION_TITLE_CLASS", () => {
  it("沿用原 pClass 的四段类名", () => {
    expect(SECTION_TITLE_CLASS).toEqual([
      "mb-[12px]!",
      "font-medium",
      "text-sm",
      "text-[var(--text-primary)]"
    ]);
  });
});
