/**
 * 投资风格箱展示口径（#2478 · 详情页「投资风格」区块）。
 *
 * 纯函数模块（组件逻辑抽离，供 vitest 直测——项目既有范式，见
 * productPositionMetrics / similarSectionMetrics / industryEmotionMetrics）。
 *
 * 口径纪律（与 backend/app/services/fund_style_service.py 一致）：
 * - 8 分类固定展示顺序（晨星式大/中/小盘 × 成长/价值 + 港股风格 + 固收风格）；
 * - value 为 0-100 暴露，同一点合计应为 100；null = 该时点该风格缺失，
 *   渲染「—」，**不补 0**（「没有暴露」与「0 暴露」是两件事）；
 * - 后端不返回颜色（契约：风格名是稳定枚举，配色由前端令牌决定）——此处用
 *   全站图表色令牌 --chart-01..08 给 8 个分类上色，颜色一律走 token（design.md 红线）；
 * - 主导风格漂移信号：dominant_changed 由后端算好，前端只透出「由 X 切换为 Y」；
 *   不自行重算或下结论。
 */

import type {
  FundStyleBox,
  FundStyleHistory,
  FundStyleItem
} from "@/api/funds";

/** 8 分类固定展示顺序（与后端 STYLE_DISPLAY_ORDER 对齐） */
export const STYLE_DISPLAY_ORDER: readonly string[] = [
  "大盘成长",
  "大盘价值",
  "中盘成长",
  "中盘价值",
  "小盘成长",
  "小盘价值",
  "港股风格",
  "固收风格"
];

/** 恐贪值展示：整数/一位小数百分比；null → 「—」 */
export function formatStyleValue(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)}%`;
}

/** 第 i 个分类对应的图表色令牌（--chart-01..08，循环兜底） */
export function styleColorVar(index: number): string {
  const n = (index % 8) + 1;
  return `--chart-${String(n).padStart(2, "0")}`;
}

/** box 是否有可展示数据（无数据后端返回 null，或有 styles 但全 null） */
export function hasStyleData(box: FundStyleBox | null): boolean {
  if (!box || !box.styles) return false;
  return box.styles.some(s => s.value != null);
}

/**
 * 按固定展示序整形 styles：后端只返回有值的风格时，缺项补 value=null（不补 0）。
 * 返回 [{ style_name, value, colorVar, index }]，index 用于稳定上色与 key。
 */
export function orderedStyles(
  box: FundStyleBox | null
): Array<FundStyleItem & { colorVar: string; index: number }> {
  if (!box || !box.styles) return [];
  const byName = new Map(box.styles.map(s => [s.style_name, s.value]));
  return STYLE_DISPLAY_ORDER.map((name, index) => ({
    style_name: name,
    value: byName.has(name) ? byName.get(name)! : null,
    colorVar: styleColorVar(index),
    index
  }));
}

export interface StyleDrift {
  /** 主导风格相较上一时点是否切换 */
  changed: boolean;
  /** 当前主导风格（可能来自 box.dominant_style 或 orderedStyles 最大值推导） */
  current: string | null;
  /** 上一时点主导风格（无则 null） */
  previous: string | null;
  /** 上一时点标识（YYYY-MM-DD），无则 null */
  prevPeriod: string | null;
}

/**
 * 主导风格漂移信号（纯透出后端结论，不重算）。
 * current 优先用后端 dominant_style；后端可能无（理论不会），则本地取 exposure 最大者。
 */
export function styleDrift(box: FundStyleBox | null): StyleDrift {
  const current =
    box?.dominant_style ??
    orderedStyles(box)
      .filter(s => s.value != null)
      .sort((a, b) => (b.value as number) - (a.value as number))[0]
      ?.style_name ??
    null;
  return {
    changed: Boolean(box?.dominant_changed),
    current,
    previous: box?.prev_dominant_style ?? null,
    prevPeriod: box?.prev_period ?? null
  };
}

/**
 * 风格漂移文案：切换时「由 X 切换为 Y」；未变且两者都有「维持 X（自 <period> 起）」。
 * 两者都缺（首次有数据）返回 null，组件据此不渲染漂移条。
 */
export function driftText(drift: StyleDrift): string | null {
  if (drift.changed) {
    if (drift.previous && drift.current) {
      return `主导风格由「${drift.previous}」切换为「${drift.current}」`;
    }
    if (drift.current) return `当前主导风格为「${drift.current}」`;
    return null;
  }
  if (drift.current && drift.prevPeriod) {
    return `主导风格维持「${drift.current}」（自 ${drift.prevPeriod} 起）`;
  }
  if (drift.current) return `当前主导风格为「${drift.current}」`;
  return null;
}

/**
 * 历史漂移序列 → echarts 多系列折线 option（8 条线，对应 8 分类，wide 转 long）。
 * 颜色走 --chart-01..08（与条形矩阵同源），但 echarts 渲到 canvas，必须传**已解析的
 * 色值**而非 CSS 变量——故由调用方注入 `colorOf(index)`（内部用 getCssVar 读 token，
 * 并在主题切换时重算）。history 为空 / 点数为 0 返回 null，组件据此隐藏图表。
 */
export function buildStyleHistoryOption(
  history: FundStyleHistory | null,
  colorOf: (index: number) => string
): unknown | null {
  if (!history || !history.points || history.points.length === 0) return null;

  // 时间轴：points 是月度倒序，折线按升序画更自然
  const pointsAsc = [...history.points].sort((a, b) =>
    a.stat_date.localeCompare(b.stat_date)
  );
  const dates = pointsAsc.map(p => p.stat_date);

  const series = STYLE_DISPLAY_ORDER.map((name, index) => ({
    name,
    type: "line",
    showSymbol: false,
    smooth: true,
    lineStyle: { width: 1.5, color: colorOf(index) },
    itemStyle: { color: colorOf(index) },
    data: pointsAsc.map(p => (name in p.styles ? p.styles[name] : null))
  }));

  return {
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: unknown) =>
        v == null ? "—" : `${(v as number).toFixed(1)}%`
    },
    legend: {
      type: "scroll",
      bottom: 0,
      textStyle: { color: "var(--text-tertiary)" },
      inactiveColor: "var(--text-disabled)"
    },
    grid: { left: 44, right: 16, top: 16, bottom: 44 },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLabel: { fontSize: 11, color: "var(--text-tertiary)" },
      axisLine: { lineStyle: { color: "var(--border-light)" } }
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      splitLine: {
        lineStyle: { color: "var(--border-light)", type: "dashed" }
      },
      axisLabel: {
        fontSize: 11,
        color: "var(--text-tertiary)",
        formatter: "{value}%"
      }
    },
    series
  };
}
