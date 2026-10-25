// 外观设置面板（#980 拆分）的**纯函数层**。
//
// 为什么抽出来：面板里六个区块的「选中下标 / 打勾颜色 / 是否展示」原本全是模板里的
// 三元表达式（`overallStyle === 'system' ? 2 : dataTheme ? 1 : 0` 这种），散在模板里
// 既没有名字也没有单测；抽成具名纯函数后，加一个新导航模式或改一档页宽不会再靠
// 「改模板 + 肉眼对下标」。
//
// 边界：**不碰状态**。所有状态仍由父组件 `useDataThemeChange()` 持有并经 props 下发，
// 子组件不各自再调一次 `useDataThemeChange()`——那个 hook 每次调用都会新建
// `dataTheme` / `overallStyle` 两个 ref（只有 `layoutTheme` / `layout` 才是共享的
// computed），子组件各自调一份会拿到互不同步的副本。

import type { OptionsType } from "@/components/ReSegmented";

/** 整体风格选项：在 `OptionsType` 之外多带一个 `theme`（Segmented 的 value 是下标） */
export interface ThemeStyleOption extends OptionsType {
  theme: string;
}

/**
 * 整体风格 → Segmented 选中下标。
 *
 * `system` 恒为 2（自动档不与明暗二选一争位），其余按 `dataTheme` 落到 1（深）/ 0（浅）。
 */
export function overallStyleIndex(
  overallStyle?: string | null,
  dataTheme?: boolean | null
): number {
  if (overallStyle === "system") return 2;
  return dataTheme ? 1 : 0;
}

/** 页签风格 → Segmented 下标（smart / card / 其余归到「谷歌」档） */
export function markIndex(markValue?: string | null): number {
  if (markValue === "smart") return 0;
  if (markValue === "card") return 1;
  return 2;
}

/** 页宽是否已设为自定义数值（`false` / 未设置时为「固定」） */
export function isStretchNumber(stretch: unknown): stretch is number {
  return typeof stretch === "number" && !Number.isNaN(stretch);
}

/** 页宽 → Segmented 下标：数字（自定义）为 1，其余为 0（固定） */
export function stretchIndex(stretch: unknown): number {
  return isStretchNumber(stretch) ? 1 : 0;
}

/** 页宽档位 → 实际值：「自定义」落 1440（区间内的中位），「固定」落 false */
export function stretchValueOf(optionValue: unknown): number | false {
  return optionValue === "custom" ? 1440 : false;
}

/**
 * 主题色块的打勾颜色。
 *
 * 未选中的色块不打勾（透明）；选中的按当前主题明暗取反色——浅色主题上用深蓝勾，
 * 其余（深色系主题）用白勾，否则勾会糊在色块里看不见。
 */
export function themeColorMark(
  current?: string | null,
  activeTheme?: string | null
): string {
  if (current !== activeTheme) return "transparent";
  return activeTheme === "light" ? "#1d2b45" : "#fff";
}

/** 整体已是暗色时隐藏「亮白色」色块：此时它与深色块几乎同色，选了看不出区别 */
export function showThemeColor(
  themeColor?: string | null,
  isDark?: boolean | null
): boolean {
  return !(themeColor === "light" && isDark);
}

/** 导航模式（顺序即渲染顺序）：`mobileHidden` 的两种在窄屏下不提供 */
export interface NavModeOption {
  layout: string;
  tip: string;
  /** 移动端不展示（顶部 / 混合菜单在窄屏没有可用形态） */
  mobileHidden?: boolean;
  ariaLabel?: string;
}

export const NAV_MODE_OPTIONS: readonly NavModeOption[] = [
  { layout: "vertical", tip: "左侧菜单，亲切熟悉" },
  { layout: "horizontal", tip: "顶部菜单，简洁概览", mobileHidden: true },
  {
    layout: "mix",
    tip: "混合菜单，灵活多变",
    mobileHidden: true,
    ariaLabel: "混合菜单"
  }
];

/** 六个区块标题的共用类名（原来父组件里的 `pClass` 计算属性） */
export const SECTION_TITLE_CLASS: readonly string[] = [
  "mb-[12px]!",
  "font-medium",
  "text-sm",
  "text-[var(--text-primary)]"
];
