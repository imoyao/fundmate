<!--
  RoadSparkline · 未竟之蹊卡片封面（走势缩略图）

  小红书式「封面大图」在这里不是照片，而是标的自己的价格曲线：
  用类型色渲染区域渐变 + 折线，涨红跌绿（--color-rise / --color-fall）。
  无历史数据时降级为「走势积累中」，不画假曲线（AGENTS.md：禁止编造数值）。

  实现要点：viewBox 固定 + preserveAspectRatio="none" 自适应卡片宽度，
  折线用 vector-effect="non-scaling-stroke" 避免横向拉伸导致线宽变形。
-->
<template>
  <div class="road-cover" :style="{ '--cover-color': color }">
    <div class="road-cover__tint" />
    <svg
      v-if="points"
      class="road-cover__chart"
      :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" :stop-color="strokeColor" stop-opacity="0.3" />
          <stop offset="100%" :stop-color="strokeColor" stop-opacity="0" />
        </linearGradient>
      </defs>
      <polygon :points="areaPoints" :fill="`url(#${gradientId})`" />
      <polyline
        :points="points"
        fill="none"
        :stroke="strokeColor"
        stroke-width="2"
        stroke-linejoin="round"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
      />
    </svg>
    <div v-else class="road-cover__empty">走势积累中</div>
    <div v-if="metricLabel" class="road-cover__metric">{{ metricLabel }}</div>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { trendChangePct } from "../helpers";

const props = withDefaults(
  defineProps<{
    /** 收盘价序列；长度 < 2 时降级为占位文案 */
    series: number[];
    /** 类型主色（封面色层与曲线的基色） */
    color?: string;
    /** 封面标注（净值/价格/点位），空字符串不渲染 */
    metricLabel?: string;
  }>(),
  { color: "var(--asset-stock)", metricLabel: "" }
);

const WIDTH = 300;
const HEIGHT = 120;
const PADDING = 10;

// 同一页面多张卡片时保证渐变 id 唯一
let seed = 0;
const gradientId = `road-cover-gradient-${(seed += 1)}-${Math.random()
  .toString(36)
  .slice(2, 8)}`;

const coordinates = computed<string[]>(() => {
  const series = props.series ?? [];
  if (series.length < 2) return [];
  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = max - min || 1;
  const step = (WIDTH - PADDING * 2) / (series.length - 1);
  return series.map((value, index) => {
    const x = PADDING + step * index;
    const y = PADDING + (HEIGHT - PADDING * 2) * (1 - (value - min) / range);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
});

const points = computed(() =>
  coordinates.value.length ? coordinates.value.join(" ") : ""
);

const areaPoints = computed(() => {
  if (!coordinates.value.length) return "";
  const last = coordinates.value[coordinates.value.length - 1].split(",")[0];
  const first = coordinates.value[0].split(",")[0];
  return `${first},${HEIGHT} ${points.value} ${last},${HEIGHT}`;
});

/** 曲线颜色按区间涨跌走涨跌语义令牌（类型色只做封面底色） */
const strokeColor = computed(() => {
  const pct = trendChangePct(props.series ?? []);
  if (pct == null || pct === 0) return "var(--text-tertiary)";
  return pct > 0 ? "var(--color-rise)" : "var(--color-fall)";
});
</script>

<style scoped>
.road-cover {
  position: relative;
  height: 132px;
  overflow: hidden;
  background: var(--bg-soft);
}

/* 类型色层：用 opacity 而非 color-mix，兼容性更稳且令牌可换肤 */
.road-cover__tint {
  position: absolute;
  inset: 0;
  background: var(--cover-color);
  opacity: 0.16;
}

.road-cover__chart {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.road-cover__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 封面标注（净值 / 价格 / 点位），与类型胶囊区分层级 */
.road-cover__metric {
  position: absolute;
  bottom: 10px;
  left: 10px;
  padding: 1px 7px;
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--glass-bg);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
}
</style>
