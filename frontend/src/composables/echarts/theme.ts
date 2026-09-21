// src/composables/echarts/theme.ts
import { ref, type Ref } from "vue";
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
