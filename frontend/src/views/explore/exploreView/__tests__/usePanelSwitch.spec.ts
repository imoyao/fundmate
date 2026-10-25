/**
 * 探市页档位映射的回归网（#980 拆分自 views/explore/index.vue）。
 *
 * 这两条规则原先藏在组件里，出错时都很安静：`?view=` 写错会白屏或错档、
 * ←/→ 在首尾不循环会让键盘用户卡住。抽成纯函数后逐条钉住。
 */

import { describe, expect, it } from "vitest";

import {
  PANEL_HINTS,
  PANEL_TABS,
  nextTabIndex,
  normalizePanel
} from "../usePanelSwitch";

describe("normalizePanel：?view= → 档位", () => {
  it("认识的两档原样透传", () => {
    expect(normalizePanel("detail")).toBe("detail");
    expect(normalizePanel("emotion")).toBe("emotion");
  });

  it("overview 与缺失值都落回概览", () => {
    expect(normalizePanel("overview")).toBe("overview");
    expect(normalizePanel(undefined)).toBe("overview");
    expect(normalizePanel("")).toBe("overview");
  });

  it("未知值不报错、不白屏，一律回概览（URL 是用户可改的）", () => {
    expect(normalizePanel("nonsense")).toBe("overview");
    expect(normalizePanel(["detail"])).toBe("overview");
    expect(normalizePanel(123)).toBe("overview");
  });
});

describe("nextTabIndex：ARIA tabs 的键盘导航", () => {
  const len = PANEL_TABS.length;

  it("→ 逐个右移", () => {
    expect(nextTabIndex("ArrowRight", 0, len)).toBe(1);
    expect(nextTabIndex("ArrowRight", 1, len)).toBe(2);
  });

  it("→ 在末项循环回首项", () => {
    expect(nextTabIndex("ArrowRight", len - 1, len)).toBe(0);
  });

  it("← 在首项循环到末项", () => {
    expect(nextTabIndex("ArrowLeft", 0, len)).toBe(len - 1);
  });

  it("Home / End 直达首尾", () => {
    expect(nextTabIndex("Home", 2, len)).toBe(0);
    expect(nextTabIndex("End", 0, len)).toBe(len - 1);
  });

  it("Enter / Space / 其它键返回 -1（交给按钮原生 click，不重复切换）", () => {
    expect(nextTabIndex("Enter", 0, len)).toBe(-1);
    expect(nextTabIndex(" ", 0, len)).toBe(-1);
    expect(nextTabIndex("Tab", 0, len)).toBe(-1);
  });
});

describe("档位常量", () => {
  it("顺序即 Tab 顺序：概览 → 深度 → 行业情绪", () => {
    expect(PANEL_TABS.map(t => t.key)).toEqual([
      "overview",
      "detail",
      "emotion"
    ]);
  });

  it("每档都有提示文案，且 Tab 与提示的 key 集合一致", () => {
    expect(Object.keys(PANEL_HINTS).sort()).toEqual(
      PANEL_TABS.map(t => t.key).sort()
    );
    PANEL_TABS.forEach(t =>
      expect(PANEL_HINTS[t.key].length).toBeGreaterThan(0)
    );
  });
});
