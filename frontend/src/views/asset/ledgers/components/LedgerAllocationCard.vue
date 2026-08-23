<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { getCssVar } from "@/composables/echarts/theme";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";

/**
 * 资产配置环形图卡（#984 ledgers/index.vue 拆分）。
 * 从 index.vue 原样迁移：数据源 overview.groups（过滤已删除账户），
 * 颜色经 getComputedStyle 读 CSS 变量（design.md 红线：禁止硬编码 hex）。
 */
const props = defineProps<{
  /** overview.groups 原始分组 */
  groups: any[];
  /** 总资产（中心覆盖层展示） */
  totalAssets: number;
}>();

// 图表颜色必须经 getComputedStyle 动态读取 CSS 变量（design.md 红线：禁止硬编码 hex）
const CHART_COLOR_VARS = [
  "--chart-01",
  "--chart-02",
  "--chart-03",
  "--chart-04",
  "--chart-05",
  "--chart-06",
  "--chart-07",
  "--chart-08"
];

function getChartColor(varName: string): string {
  return getCssVar(varName);
}

// 环形图数据源：overview groups（过滤已删除账户），value 用 group.total（元）
const allocationGroups = computed(() =>
  (props.groups ?? []).filter(
    (g: any) => g.type !== "deleted" && (g.total || 0) > 0
  )
);

// 空态判定：无分组或全部 total=0 时不渲染图表
const hasAllocationData = computed(() => allocationGroups.value.length > 0);

// 环形图 option：环形 + 底部 legend（分类名 + 占比），中心由 HTML 覆盖层显示总资产
const allocationOption = computed(() => {
  const groups = allocationGroups.value;
  const total = groups.reduce((sum: number, g: any) => sum + (g.total || 0), 0);
  const legendTextColor = getChartColor("--text-secondary") || "#6b655c";
  const borderColor = getChartColor("--bg-card") || "#ffffff";
  // 尊重系统减弱动效偏好：关闭 echarts 入场动画
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  return {
    animation: !reduceMotion,
    tooltip: {
      trigger: "item",
      backgroundColor: getChartColor("--bg-card") || "#ffffff",
      borderColor: getChartColor("--border-light") || "#f0ebe4",
      textStyle: {
        color: getChartColor("--text-primary") || "#2d2a24",
        fontSize: 12
      },
      formatter: (params: any) => {
        const pct = total > 0 ? ((params.value / total) * 100).toFixed(1) : "0";
        return `${params.name}<br/>¥${Number(params.value).toLocaleString()}（${pct}%）`;
      }
    },
    legend: {
      bottom: 0,
      icon: "circle",
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 12,
      textStyle: { color: legendTextColor, fontSize: 12 },
      // 分类名 + 占比（%），占比按 total 实时计算
      formatter: (name: string) => {
        const g = groups.find((x: any) => x.label === name);
        const pct =
          total > 0 ? (((g?.total || 0) / total) * 100).toFixed(1) : "0";
        return `${name} ${pct}%`;
      }
    },
    series: [
      {
        type: "pie",
        radius: ["52%", "72%"],
        center: ["50%", "42%"],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 6,
          borderColor,
          borderWidth: 2
        },
        label: { show: false },
        emphasis: { scaleSize: 4 },
        // 颜色按 CHART_COLOR_VARS 循环取用，超出 8 类时循环回绕
        data: groups.map((g: any, i: number) => ({
          name: g.label,
          value: g.total,
          itemStyle: {
            color: getChartColor(CHART_COLOR_VARS[i % CHART_COLOR_VARS.length])
          }
        }))
      }
    ]
  };
});
</script>

<template>
  <div class="overview-card allocation-card">
    <p class="text-sm mb-2" :style="{ color: 'var(--text-tertiary)' }">
      资产配置
    </p>
    <div v-if="hasAllocationData" class="allocation-chart-wrap">
      <!-- 中心覆盖层：总资产金额（HTML 层，复用 MoneyDisplay 样式锚点） -->
      <div class="allocation-center">
        <span
          class="allocation-center-label"
          :style="{ color: 'var(--text-tertiary)' }"
          >总资产</span
        >
        <MoneyDisplay
          :value="totalAssets"
          :show-sign="false"
          :auto-color="false"
          size="sm"
        />
      </div>
      <v-chart
        :option="allocationOption"
        :autoresize="true"
        class="allocation-chart"
      />
    </div>
    <div v-else class="allocation-empty">
      <IconifyIconOffline
        icon="ep:pie-chart"
        class="text-4xl mb-2 opacity-30"
      />
      <p class="text-sm" :style="{ color: 'var(--text-tertiary)' }">
        暂无资产配置数据
      </p>
    </div>
  </div>
</template>

<style scoped>
@media (prefers-reduced-motion: reduce) {
  .allocation-card {
    transition: none;
  }
}

.allocation-card {
  display: flex;
  flex-direction: column;
}

.allocation-chart-wrap {
  position: relative;
  flex: 1;
  min-height: 220px;
}

/* 图表绝对定位填满容器：避免 echarts 在 flex 高度解析下拿到 0 高度 */
.allocation-chart {
  position: absolute;
  inset: 0;
}

/* 环形图中心覆盖层：总资产金额（HTML 层，与 series center: 42% 对齐） */
.allocation-center {
  position: absolute;
  top: 42%;
  left: 50%;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  pointer-events: none;
  transform: translate(-50%, -50%);
}

.allocation-center-label {
  font-size: var(--text-label, 13px);
  line-height: 18px;
}

.allocation-empty {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  color: var(--text-tertiary);
}
</style>
