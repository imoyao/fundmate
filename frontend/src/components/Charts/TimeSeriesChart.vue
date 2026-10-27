<!--
  通用多序列折线（#2685）：只负责「把后端算好的序列画出来」，不做任何口径计算。

  - `data` 里的 `null` **默认断线**（`connectNulls=false`）：缺价 / 基准不可算的日期
    补 0 会被读成「当天收益归零 / 基准走平」，比留空更误导；
  - 颜色一律读 CSS 变量（design.md 禁止硬编码色值），暗色切换由 `useThemeTick` 触发重算；
  - 空数据由调用方 `v-if` 决定，本组件不画「暂无数据」占位（那是面板的职责）。
-->
<template>
  <div class="ts-chart" :style="{ height: `${height}px` }">
    <VChart :option="option" autoresize />
  </div>
</template>

<script lang="ts">
/** 一条折线：数据与后端序列一一对应（长度 = categories 长度） */
export type TimeSeriesItem = {
  name: string;
  data: Array<number | null>;
  /** CSS 变量名（如 `--brand-600`）；不传按序取默认调色板 */
  colorVar?: string;
  /** 虚线：辅助口径（如基准），与主口径区分 */
  dashed?: boolean;
  /** 阶梯线：累计型指标 */
  step?: "start" | "middle" | "end";
  /** 是否跨接 null（默认 false = 断线） */
  connectNulls?: boolean;
};
</script>

<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { getCssVar, useThemeTick } from "@/composables/echarts/theme";

defineOptions({ name: "TimeSeriesChart" });

const props = withDefaults(
  defineProps<{
    categories: string[];
    series: TimeSeriesItem[];
    /** 数值单位后缀（如 `%`），tooltip 与 y 轴共用 */
    unit?: string;
    height?: number;
  }>(),
  { unit: "%", height: 240 }
);

/** 主口径优先用品牌色，其余按墨色层级退让——不抢主线的视觉权重 */
const DEFAULT_COLORS = ["--brand-600", "--text-tertiary", "--color-fall"];

const themeTick = useThemeTick();

function token(name: string, fallback: string): string {
  void themeTick.value; // 暗色切换时重算 option，触发重绘（#976）
  return getCssVar(name, fallback);
}

const option = computed(() => {
  const axisColor = token("--text-tertiary-ink", "#8c8478");
  const splitColor = token("--border-subtle", "#f0ebe4");
  const fmt = (v: number | null) =>
    v === null || v === undefined ? "—" : `${v.toFixed(2)}${props.unit}`;

  return {
    tooltip: { trigger: "axis", valueFormatter: fmt },
    legend: {
      top: 0,
      icon: "roundRect",
      itemWidth: 10,
      itemHeight: 2,
      textStyle: { color: axisColor }
    },
    grid: { left: 56, right: 16, top: 34, bottom: 28 },
    xAxis: {
      type: "category",
      data: props.categories,
      boundaryGap: false,
      axisLine: { lineStyle: { color: splitColor } },
      axisLabel: { color: axisColor, hideOverlap: true },
      axisTick: { show: false }
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: {
        color: axisColor,
        formatter: (v: number) => `${v}${props.unit}`
      },
      splitLine: { lineStyle: { color: splitColor } }
    },
    series: props.series.map((item, index) => {
      const color = token(
        item.colorVar ?? DEFAULT_COLORS[index % DEFAULT_COLORS.length],
        "#8c8478"
      );
      return {
        name: item.name,
        type: "line",
        data: item.data,
        showSymbol: false,
        step: item.step ?? false,
        connectNulls: item.connectNulls ?? false,
        lineStyle: {
          width: 2,
          type: item.dashed ? "dashed" : "solid",
          color
        },
        itemStyle: { color }
      };
    })
  };
});
</script>

<style scoped>
.ts-chart {
  width: 100%;
}
</style>
