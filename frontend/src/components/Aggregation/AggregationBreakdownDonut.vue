<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import {
  getCssVar,
  getChartPalette,
  useThemeTick
} from "@/composables/echarts/theme";
import type { AggregationTypeBreakdownItem } from "@/api/ledger";

/**
 * 资产构成环形图（#1224）：按基金类型展示市值占比。
 *
 * 原为 `AggregationHero` 内联实现，拆分时整块搬出（#980）——环形图配色、图例折叠规则
 * （前 5 类 + 其余合并为「其他」）与占比口径均未改动，只是换了个宿主文件。
 * 无数据或市值全为 0 时自身不渲染，父级 flex 布局与原先 `v-if` 的表现一致。
 */
defineOptions({ name: "AggregationBreakdownDonut" });

const props = withDefaults(
  defineProps<{
    /** 资产构成：按基金类型聚合的市值分布 */
    items?: AggregationTypeBreakdownItem[] | null;
  }>(),
  { items: null }
);

/** 过滤市值为 0 的构成项（避免空持仓画出无意义扇区） */
const breakdownItems = computed<AggregationTypeBreakdownItem[]>(() =>
  (props.items ?? []).filter(x => (x.market_value_cents || 0) > 0)
);
const hasBreakdown = computed(() => breakdownItems.value.length > 0);
const breakdownTotal = computed(() =>
  breakdownItems.value.reduce((sum, x) => sum + x.market_value_cents, 0)
);
/** 图例只列前 5 类，其余折叠为「其他」 */
const legendTop = computed(() => breakdownItems.value.slice(0, 5));
const restCount = computed(() => Math.max(0, breakdownItems.value.length - 5));
const restTotal = computed(() =>
  breakdownItems.value
    .slice(5)
    .reduce((sum, x) => sum + x.market_value_cents, 0)
);

function pctOf(cents: number): string {
  const total = breakdownTotal.value;
  return total > 0 ? ((cents / total) * 100).toFixed(1) : "0";
}

const themeTick = useThemeTick();
/** 8 色分类配色板（实时读 CSS 语义变量，design.md 红线：禁止硬编码 hex）。
 * 用 computed 依赖 themeTick，主题切换时重读配色板（#976） */
const donutPalette = computed(() => {
  void themeTick.value;
  return getChartPalette();
});

const donutOption = computed(() => {
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return {
    animation: !reduceMotion,
    tooltip: {
      trigger: "item",
      backgroundColor: getCssVar("--bg-card") || "#ffffff",
      borderColor: getCssVar("--border-light") || "#f0ebe4",
      textStyle: {
        color: getCssVar("--text-primary") || "#2d2a24",
        fontSize: 12
      },
      formatter: (params: any) => {
        const pct = pctOf((params.value as number) * 100);
        return `${params.name}<br/>¥${Number(params.value).toLocaleString()}（${pct}%）`;
      }
    },
    series: [
      {
        type: "pie",
        radius: ["58%", "80%"],
        center: ["50%", "50%"],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 6,
          borderColor: getCssVar("--bg-card") || "#ffffff",
          borderWidth: 2
        },
        label: { show: false },
        emphasis: { scaleSize: 4 },
        data: breakdownItems.value.map((x, i) => ({
          name: x.name,
          value: x.market_value_cents / 100,
          itemStyle: {
            color: donutPalette.value[i % donutPalette.value.length]
          }
        }))
      }
    ]
  };
});
</script>

<template>
  <div v-if="hasBreakdown" class="hero-donut-block">
    <div class="hero-donut">
      <v-chart :option="donutOption" :autoresize="true" class="donut-chart" />
      <div class="donut-center">
        <span class="donut-center-label">资产构成</span>
        <span class="donut-center-count">{{ breakdownItems.length }} 类</span>
      </div>
    </div>
    <div class="hero-legend">
      <div
        v-for="(item, i) in legendTop"
        :key="item.name"
        class="legend-item"
        :title="`¥${(item.market_value_cents / 100).toLocaleString()}`"
      >
        <span
          class="legend-dot"
          :style="{ background: donutPalette[i % donutPalette.length] }"
        />
        <span class="legend-name">{{ item.name }}</span>
        <span class="legend-pct">{{ pctOf(item.market_value_cents) }}%</span>
      </div>
      <div v-if="restCount > 0" class="legend-item">
        <span class="legend-dot legend-dot--rest" />
        <span class="legend-name">其他 {{ restCount }} 类</span>
        <span class="legend-pct">{{ pctOf(restTotal) }}%</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── 资产构成环形图（#1224）── */
.hero-donut-block {
  display: flex;
  flex: none;
  gap: var(--space-compact);
  align-items: center;
}

.hero-donut {
  position: relative;
  flex: none;
  width: 148px;
  height: 148px;
}

.donut-chart {
  position: absolute;
  inset: 0;
}

.donut-center {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  pointer-events: none;
  transform: translate(-50%, -50%);
}

.donut-center-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.donut-center-count {
  font-size: var(--text-num-strong);
  font-weight: 600;
  color: var(--text-primary);
}

.hero-legend {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.legend-item {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: var(--text-label);
  line-height: 1.2;
  white-space: nowrap;
}

.legend-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-dot--rest {
  background: var(--text-tertiary);
  opacity: 0.5;
}

.legend-name {
  color: var(--text-secondary);
}

.legend-pct {
  min-width: 44px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
  text-align: right;
}

@media (width <= 768px) {
  .hero-donut-block {
    justify-content: center;
  }
}
</style>
