// src/composables/echarts/theme.ts
/**
 * ECharts 取色工具。
 * 设计红线（见 frontend/design.md）：图表颜色一律走 CSS 语义变量，禁止硬编码 hex。
 * 暗色模式由 [data-theme="dark"] 自动切换，业务/图表代码不判断主题。
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
  ].map((token) => getCssVar(token));
}
