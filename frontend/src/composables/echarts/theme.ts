// src/composables/echarts/theme.ts
import { ref, type Ref } from "vue";
/**
 * ECharts 取色工具。
 * 设计红线（见 frontend/design.md）：图表颜色一律走 CSS 语义变量，禁止硬编码 hex。
 * 暗色模式由 <html> 上的 .dark 类（dark.scss 的 `:root.dark` 覆盖同名变量）自动切换，
 * 业务/图表代码不判断主题。注意不是 data-theme 属性——它只承载配色主题名。
 */

/**
 * 读取 CSS 自定义属性（语义色变量），返回 trim 后的字符串。
 * @param name 变量名，含前导 `--`，如 "--color-rise"
 * @param fallback 变量未定义时的回退值（默认空串）
 */
export function getCssVar(name: string, fallback = ""): string {
  if (typeof window === "undefined") return fallback;
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name);
  const trimmed = raw.trim();
  return trimmed || fallback;
}

/** hex（3/6 位）→ `rgba()`；非 hex（如变量未定义、空串）回退黑色透明 */
function hexToRgba(hex: string, alpha: number): string {
  if (!/^#[0-9a-fA-F]{3,8}$/.test(hex)) return `rgba(0, 0, 0, ${alpha})`;
  let r = 0,
    g = 0,
    b = 0;
  if (hex.length === 4) {
    r = parseInt(hex[1] + hex[1], 16);
    g = parseInt(hex[2] + hex[2], 16);
    b = parseInt(hex[3] + hex[3], 16);
  } else {
    r = parseInt(hex.slice(1, 3), 16);
    g = parseInt(hex.slice(3, 5), 16);
    b = parseInt(hex.slice(5, 7), 16);
  }
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * 读取 CSS 语义色变量并叠加透明度 → `rgba()`。
 * 用于图表面积渐变等「同色系不同透明度」场景（#2156：净值走势面积渐变
 * 原先硬编码 `rgba(255,107,0,…)`，与折线 `--brand-700` 不同色）。
 * 变量取不到时回退 fallback（同样按 hex 解析），fallback 也未定义则返回黑色透明。
 */
export function getCssVarWithAlpha(
  name: string,
  alpha: number,
  fallback = ""
): string {
  return hexToRgba(getCssVar(name, fallback), alpha);
}

/** 图表常用语义色 token（与 design.md / design.dark.md 对齐，集中维护避免散落硬编码） */
export const CHART_TOKENS = {
  rise: "--color-rise",
  fall: "--color-fall",
  brand700: "--brand-700",
  info: "--color-info",
  neutral: "--color-neutral",
  warning: "--color-warning",
  success: "--color-success",
  accent: "--color-accent",
  textPrimary: "--text-primary",
  textSecondary: "--text-secondary",
  textTertiary: "--text-tertiary",
  borderLight: "--border-light",
  borderDefault: "--border-default",
  bgCard: "--bg-card"
} as const;

/**
 * 上述 token 的**亮色回退值**（单一来源，#2314）。
 *
 * 为什么需要：ECharts 不解析 `var(--x)`，颜色必须命令式读取后传入；CSS 变量
 * 偶发取不到时（首帧 / 卸载竞态） fallback 是唯一兜底。原实现各组件各自手写
 * fallback，且用的是 Element 旧色板（#409eff / #e6a23c / #9aa0a6 / #287d51）——
 * 一旦真触发，暖色页面里会跳出冷蓝橙灰。本表取值 = colors.css 亮色现值，
 * 改令牌时回来同步；暗色由 getCssVar 读到的暗色值承担，不走本表。
 */
export const CHART_FALLBACKS: Record<keyof typeof CHART_TOKENS, string> = {
  rise: "#e34f38",
  fall: "#7bc49a",
  brand700: "#e34f38",
  info: "#7a9aa8",
  neutral: "#8e8b82",
  warning: "#d4c898",
  success: "#81b29a",
  accent: "#b88a8a",
  textPrimary: "#2d2a24",
  textSecondary: "#6b655c",
  textTertiary: "#8c8478",
  borderLight: "#f0ebe4",
  borderDefault: "#e5ddd4",
  bgCard: "#ffffff"
};

/** 图表分类配色板（8 色，与 design.md Data Visualization 对齐），调用时实时读取当前主题变量 */
export function getChartPalette(): string[] {
  return [
    "--chart-01",
    "--chart-02",
    "--chart-03",
    "--chart-04",
    "--chart-05",
    "--chart-06",
    "--chart-07",
    "--chart-08"
  ].map(token => getCssVar(token));
}

/**
 * 主题切换响应式信号（#976 ECharts 暗色重绘治本）。
 *
 * 问题：图表颜色经 getCssVar 命令式读取。vue-echarts 的 `chartOption`(computed) 与
 * useEchartsLifecycle 的 setOption 都不建立 Vue 响应式依赖——切暗色后 CSS 变量已变，
 * 但 computed 不重算、composable 不重绘，图表停留在旧主题配色。
 *
 * 解：模块级单例 MutationObserver 监听 documentElement 的 `class` / `data-theme` 变化，
 * 变化时 themeTick +1；图表 computed / watch 读取 themeTick 即触发重绘。全站只注册一个 observer。
 */
export const themeTick = ref(0);

let observerStarted = false;
function startThemeObserver() {
  if (observerStarted || typeof window === "undefined") return;
  observerStarted = true;
  const handler = () => {
    themeTick.value++;
  };
  new MutationObserver(handler).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class", "data-theme"]
  });
}

/** 组件内调用：确保 observer 已启动，返回 themeTick 供 computed / watch 建立依赖。 */
export function useThemeTick(): Ref<number> {
  startThemeObserver();
  return themeTick;
}
