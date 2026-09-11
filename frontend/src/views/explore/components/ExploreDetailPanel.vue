<!-- frontend/src/views/explore/components/ExploreDetailPanel.vue -->
<!--
  探市「深度」档（方案 D，2026-09-12）：
  由原 /temperature 页面整体迁移而来。header / footer / 未登录引导条已剥离
  （由父页面 views/explore/index.vue 统一提供），仅保留温度画像主体内容。
-->
<template>
  <div v-loading="loading" class="detail-panel">
    <!-- 综合仪表盘 -->
    <section class="dashboard-section">
      <MetricGrid>
        <!-- 综合温度仪表（大） -->
        <TemperatureGaugeCard
          :value="compositeValue"
          title="综合市场温度"
          :level="compositeLevel"
          caption="基于多源市场数据计算"
          :updated-at="updatedAt"
          size="lg"
          featured
        />

        <!-- 核心指标卡片 -->
        <MetricCard
          v-for="metric in coreMetrics"
          :key="metric.key"
          :title="metric.title"
          :value="metric.value"
          :unit="metric.unit"
          :level="metric.level"
        />
      </MetricGrid>
    </section>

    <!-- 温度解读 + 市场机会：与仪表卡配套，放在趋势图上方 -->
    <section class="context-section">
      <div class="context-grid">
        <TemperatureContextCard
          :temperature="compositeValue"
          :fear-greed="fearGreedValue"
          :fear-greed-label="fearGreedLabel"
          :periods="tempPeriods"
          caption="综合 6 个市场指标与市场情绪推导"
          class="context-card"
        />

        <!-- 市场机会（来自 temperature store，由综合温度与股债性价比推导） -->
        <div v-if="tempStore.opportunityList.length" class="opportunity-card">
          <SectionHeader title="市场机会" />
          <div class="opportunity-list">
            <div
              v-for="op in tempStore.opportunityList"
              :key="op.name"
              class="opportunity-item"
              :class="`opportunity-item--${op.tone}`"
            >
              <div class="opportunity-head">
                <span class="opportunity-name">{{ op.name }}</span>
                <span class="opportunity-tag">{{
                  op.tone === "safe"
                    ? "机会"
                    : op.tone === "danger"
                      ? "风险"
                      : "中性"
                }}</span>
              </div>
              <p class="opportunity-desc">{{ op.desc }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 温度趋势图 -->
    <section class="chart-section">
      <SectionHeader title="综合温度趋势">
        <template #action>
          <el-radio-group
            v-model="historyDays"
            size="small"
            @change="fetchHistory"
          >
            <el-radio-button :value="30">30天</el-radio-button>
            <el-radio-button :value="90">90天</el-radio-button>
            <el-radio-button :value="180">半年</el-radio-button>
          </el-radio-group>
        </template>
      </SectionHeader>
      <div class="chart-wrapper">
        <v-chart
          ref="chartRef"
          :option="chartOption"
          :autoresize="true"
          style="width: 100%; height: 300px"
        />
      </div>
    </section>

    <!-- 行业乖离度排行：表格形式，支持排序筛选 -->
    <BiasTable
      :items="biasItems"
      :date="biasDate"
      :stale="biasStale"
      :loading="biasLoading"
    />

    <!-- 行业拥挤度排行：表格形式，与乖离度并列（不同维度） -->
    <CrowdingTable
      :items="crowdingValidItems"
      :date="crowdingDate"
      :stale="crowdingStale"
      :loading="crowdingLoading"
    />

    <!-- 全部市场温度指标：紧凑表格 -->
    <MetricDetailTable :items="detailMetrics" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import VChart from "vue-echarts";
import { getTemperatureHistory, getMultiItems } from "@/api/temperature";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import TemperatureContextCard from "@/components/TemperatureContextCard/index.vue";
import { useTemperatureStore } from "@/store/modules/temperature";
import { getCssVar } from "@/composables/echarts/theme";
import { useTemperatureOverview } from "@/composables/temperature/useTemperatureOverview";
import { CORE_SINGLE_SOURCES } from "@/constants/temperature";
import BiasTable from "./detail/BiasTable.vue";
import CrowdingTable from "./detail/CrowdingTable.vue";
import MetricDetailTable from "./detail/MetricDetailTable.vue";

defineOptions({
  name: "ExploreDetailPanel"
});

// 温度三色：动态读取全局 token（src/style/colors.css 的 --temp-*），
// 保持与页面其它元素单一来源、视觉一致（design.md 红线：图表颜色用 getComputedStyle 读取）
// 用 computed 实时读取：暗色切换时 CSS 变量变化可正确重读（原模块顶层一次性求值缺陷修复）
function readTempColorVar(name: string): string {
  return getCssVar(name, "#888");
}

const TEMP_COLORS = computed(() => ({
  low: readTempColorVar("--temp-low"),
  mid: readTempColorVar("--temp-mid"),
  high: readTempColorVar("--temp-high")
}));

// 图表渐变需要具体色值：把 CSS 变量读出的 hex 转 rgba（透明度按原视觉保留）。
// 原实现硬编码 rgba(227, 79, 56, ...)（= --color-rise 亮色值），现改为实时读取语义变量，
// 暗色模式（--color-rise: #d45a44）自动适配（design.md 红线：图表颜色禁止硬编码）
function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

// ================================================================
// 市场温度总览数据（两页共用 composable，见 #980）
// 解析 getTemperatureOverview 的 singles/composites，产出页面所需 refs 与 fetchTemperature()
// ================================================================
const {
  loading,
  overview,
  compositeTemperature,
  selfCalcPercent,
  selfCalcLevel,
  volumeData,
  fearData,
  cbTemperature,
  cbLabel,
  fetchTemperature
} = useTemperatureOverview();

// ================================================================
// 数据状态（页面独立数据：历史趋势 / 多指标接口，composable 未覆盖）
// ================================================================
const historyData = ref<{
  dates: string[];
  values: (number | null)[];
  levels?: string[];
}>({ dates: [], values: [] });
const historyDays = ref(90);
const biasItems = ref<any[]>([]);
const biasDate = ref<string>("");
const biasStale = ref(false);
const biasLoading = ref(false);
const chartRef = ref<any>(null);

// 行业拥挤度（独立维度：行业 PB / 全A 中位 PB 历史百分位）
const crowdingItems = ref<any[]>([]);
const crowdingDate = ref<string>("");
const crowdingStale = ref(false);
const crowdingLoading = ref(false);

// ================================================================
// 计算属性
// ================================================================
const updatedAt = computed(() => overview.value?.updated_at || "");

// 综合温度（composable 已解析 composites.composite_temperature）
const compositeValue = computed(
  () => compositeTemperature.value?.value ?? null
);

const compositeLevel = computed(() => compositeTemperature.value?.level || "");

// 温度解读卡（TemperatureContextCard）所需数据，从 composable 的 fearData 推导
const fearGreedValue = computed<number | null>(() => {
  const v = fearData.value?.value;
  return typeof v === "number" ? v : null;
});
const fearGreedLabel = computed(() => fearData.value?.label || "");
const tempPeriods = computed(() => {
  const bands = overview.value?.composites?.temperature_bands;
  if (!bands) return [];
  return (["short", "medium", "long"] as const)
    .map(k => bands[k])
    .filter(Boolean)
    .map((b: { name?: string; value?: number }) => ({
      label: b.name || "",
      value: typeof b.value === "number" ? b.value : null
    }));
});

// 核心指标（从 composable 已解析的 refs 聚合，不再重复解析 overview）
const coreMetrics = computed(() => {
  const result = [];

  // 恐惧贪婪
  if (fearData.value) {
    result.push({
      key: "fear",
      title: "恐惧贪婪",
      value: fearData.value.value,
      level: fearData.value.label
    });
  }

  // 股债性价比
  if (selfCalcPercent.value != null) {
    result.push({
      key: "self_calc",
      title: "股债性价比",
      value: selfCalcPercent.value,
      unit: "%",
      level: selfCalcLevel.value
    });
  }

  // 可转债温度
  if (cbTemperature.value != null) {
    result.push({
      key: "cb",
      title: "可转债",
      value: cbTemperature.value,
      unit: "°",
      level: cbLabel.value
    });
  }

  // 成交额
  if (volumeData.value) {
    result.push({
      key: "volume",
      title: "成交额",
      value: volumeData.value.value,
      unit: "亿",
      level: volumeData.value.label
    });
  }

  return result;
});

// 全部单值指标（过滤核心指标，按数据分层展示）
const detailMetrics = computed(() => {
  const singles = overview.value?.singles || [];
  return singles.filter((s: any) => !CORE_SINGLE_SOURCES.includes(s.source));
});

// 过滤整组标灰占位（item_code === '__NA__'），仅展示有效行业
const crowdingValidItems = computed(() =>
  (crowdingItems.value || []).filter((i: any) => i.item_code !== "__NA__")
);

// ECharts 配置
const chartOption = computed(() => {
  const dates = historyData.value.dates || [];
  const values = historyData.value.values || [];
  const levels = historyData.value.levels || [];

  // 计算颜色：根据 level 决定（复用 TEMP_COLORS，与全局 token 一致）
  const colors = levels.map(level => {
    if (level === "偏低" || level === "低估") return TEMP_COLORS.value.low;
    if (level === "偏高" || level === "高估") return TEMP_COLORS.value.high;
    return TEMP_COLORS.value.mid;
  });

  return {
    tooltip: {
      trigger: "axis",
      formatter: (params: any) => {
        const p = params[0];
        const idx = p.dataIndex;
        const level = levels[idx] || "";
        return `${p.axisValue}<br/>综合温度: ${p.value}°<br/>等级: ${level}`;
      }
    },
    grid: {
      left: 50,
      right: 20,
      top: 20,
      bottom: 30
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: {
        rotate: 30,
        fontSize: 11
      }
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      splitLine: {
        lineStyle: { color: "var(--border-light)", type: "dashed" }
      },
      axisLabel: {
        formatter: "{value}°",
        fontSize: 11
      }
    },
    series: [
      {
        name: "综合温度",
        type: "line",
        data: values,
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: {
          color: "var(--brand-700)",
          width: 2
        },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            // 涨色渐变：实时读取 --color-rise（原硬编码 rgba(227, 79, 56, ...) 即其亮色值），
            // 暗色模式自动适配，透明度按原视觉保留
            colorStops: [
              {
                offset: 0,
                color: hexToRgba(getCssVar("--color-rise", "#e34f38"), 0.3)
              },
              {
                offset: 1,
                color: hexToRgba(getCssVar("--color-rise", "#e34f38"), 0.05)
              }
            ]
          }
        },
        itemStyle: {
          color: (params: any) => {
            const idx = params.dataIndex;
            return colors[idx] || "var(--brand-700)";
          }
        },
        markLine: {
          silent: true,
          data: [
            {
              yAxis: 70,
              label: {
                formatter: "偏高",
                color: "var(--text-tertiary)",
                fontSize: 11
              }
            },
            {
              yAxis: 40,
              label: {
                formatter: "适中",
                color: "var(--text-tertiary)",
                fontSize: 11
              }
            },
            {
              yAxis: 25,
              label: {
                formatter: "偏低",
                color: "var(--text-tertiary)",
                fontSize: 11
              }
            }
          ],
          lineStyle: {
            color: "var(--border-default)",
            type: "dashed",
            width: 1
          }
        }
      }
    ]
  };
});

// ================================================================
// 方法
// ================================================================
const fetchHistory = async () => {
  try {
    const res = await getTemperatureHistory(historyDays.value);
    historyData.value = res.data;
  } catch (e) {
    console.error("获取历史趋势失败:", e);
  }
};

const fetchBias = async () => {
  biasLoading.value = true;
  try {
    const res = await getMultiItems("bias");
    const data = res.data;
    if (data && data.items) {
      biasItems.value = data.items;
      biasDate.value = data.date || "";
      biasStale.value =
        Boolean(data.stale) || (data.items || []).some((i: any) => i.stale);
    } else {
      biasItems.value = [];
      biasStale.value = false;
    }
  } catch (e) {
    console.error("获取乖离率数据失败:", e);
    biasItems.value = [];
  } finally {
    biasLoading.value = false;
  }
};

const fetchCrowding = async () => {
  crowdingLoading.value = true;
  try {
    const res = await getMultiItems("industry_crowding");
    const data = res.data;
    if (data && data.items) {
      crowdingItems.value = data.items;
      crowdingDate.value = data.date || "";
      crowdingStale.value =
        Boolean(data.stale) || (data.items || []).some((i: any) => i.stale);
    } else {
      crowdingItems.value = [];
      crowdingStale.value = false;
    }
  } catch (e) {
    console.error("获取行业拥挤度数据失败:", e);
    crowdingItems.value = [];
  } finally {
    crowdingLoading.value = false;
  }
};

// 温度 store：承载综合温度、股债性价比与市场机会清单
const tempStore = useTemperatureStore();

// ================================================================
// 生命周期
// ================================================================
onMounted(async () => {
  await fetchTemperature();
  await fetchHistory();
  await fetchBias();
  await fetchCrowding();
  // NOTE: 与 tempStore.fetchTemperature 各自调用一次 getTemperatureOverview，后续可合并为单一数据源
  await tempStore.fetchTemperature();
});

// 当历史天数变化时重新获取
watch(historyDays, () => {
  fetchHistory();
});
</script>

<style lang="scss" scoped>
/* ===== 响应式 ===== */
@media (width <= 960px) {
  .context-grid {
    grid-template-columns: 1fr;
  }
}

@media (width <= 768px) {
  .detail-panel {
    padding: 16px;
  }
}

/* 深度档容器：与概览档共用同一套页面边距与最大宽度 */
.detail-panel {
  max-width: 1280px;
  padding: var(--space-standard) 24px 16px;
  margin: 0 auto;
}

/* 仪表盘区域 */
.dashboard-section {
  margin-bottom: 24px;
}

.context-section {
  margin-bottom: 24px;
}

/* 图表区域 */
.chart-section {
  padding: 20px 24px;
  margin-bottom: 24px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.chart-wrapper {
  width: 100%;
  height: 300px;
}

/* ============================================================
   温度解读 + 市场机会（并排）
   ============================================================ */
.context-grid {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 16px;
  align-items: stretch;
}

.context-card,
.opportunity-card {
  overflow: hidden;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.opportunity-card {
  display: flex;
  flex-direction: column;
  padding: 16px;
}

.opportunity-card :deep(.section-header) {
  margin-bottom: 12px;
}

.opportunity-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
}

.opportunity-item {
  padding: 12px 14px;
  background: var(--bg-subtle);
  border-left: 4px solid var(--border-light);
  border-radius: 10px;
}

.opportunity-item--safe {
  background: color-mix(in srgb, var(--temp-low) 8%, var(--bg-subtle));
  border-left-color: var(--temp-low);
}

.opportunity-item--danger {
  background: color-mix(in srgb, var(--temp-high) 8%, var(--bg-subtle));
  border-left-color: var(--temp-high);
}

.opportunity-item--neutral {
  background: color-mix(in srgb, var(--temp-mid) 8%, var(--bg-subtle));
  border-left-color: var(--temp-mid);
}

.opportunity-head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.opportunity-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.opportunity-tag {
  padding: 2px 8px;
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  background: var(--border-light);
  border-radius: 10px;
}

.opportunity-item--safe .opportunity-tag {
  color: var(--temp-low);
  background: color-mix(in srgb, var(--temp-low) 18%, transparent);
}

.opportunity-item--danger .opportunity-tag {
  color: var(--temp-high);
  background: color-mix(in srgb, var(--temp-high) 18%, transparent);
}

.opportunity-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
}

/* 表格视觉基线由全站统一主题维护（src/style/el-table.css），勿在本页 :deep 覆盖 */
</style>
