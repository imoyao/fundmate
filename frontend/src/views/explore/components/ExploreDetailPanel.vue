<!-- frontend/src/views/explore/components/ExploreDetailPanel.vue -->
<!--
  探市「深度」档（方案 D，2026-09-12）：由原温度计页面整体迁移而来。
  header / footer / 未登录引导条已剥离（由父页面 views/explore/index.vue 统一提供）。

  2026-09-12 按 #980 拆分：核心指标清单收口到 useCoreMetrics、
  趋势图抽为 TemperatureTrendChart，本文件只做区域编排。
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

        <!-- 核心指标（恐惧贪婪 / 股债性价比 / 可转债 / 成交额）：清单见 useCoreMetrics -->
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

    <!-- 综合温度趋势（自带标题栏、周期切换与取数） -->
    <TemperatureTrendChart />

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
import { ref, computed, onMounted } from "vue";
import { getMultiItems } from "@/api/temperature";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import TemperatureContextCard from "@/components/TemperatureContextCard/index.vue";
import { useTemperatureStore } from "@/store/modules/temperature";
import { useTemperatureOverview } from "@/composables/temperature/useTemperatureOverview";
import { useCoreMetrics } from "@/composables/temperature/useCoreMetrics";
import { CORE_SINGLE_SOURCES } from "@/constants/temperature";
import TemperatureTrendChart from "./TemperatureTrendChart.vue";
import BiasTable from "./detail/BiasTable.vue";
import CrowdingTable from "./detail/CrowdingTable.vue";
import MetricDetailTable from "./detail/MetricDetailTable.vue";

defineOptions({
  name: "ExploreDetailPanel"
});

// ================================================================
// 市场温度总览：与概览档共享同一份数据实例（单例 + 并发去重，见该 composable 头注释）
// ================================================================
const { loading, overview, compositeTemperature, fearData, fetchTemperature } =
  useTemperatureOverview();

// 核心指标清单收口在 useCoreMetrics（见 #980）
const { coreMetrics } = useCoreMetrics();

// ================================================================
// 页面独立数据：多指标接口（composable 未覆盖）
// ================================================================
const biasItems = ref<any[]>([]);
const biasDate = ref<string>("");
const biasStale = ref(false);
const biasLoading = ref(false);

// 行业拥挤度（独立维度：行业 PB / 全A 中位 PB 历史百分位）
const crowdingItems = ref<any[]>([]);
const crowdingDate = ref<string>("");
const crowdingStale = ref(false);
const crowdingLoading = ref(false);

// ================================================================
// 计算属性
// ================================================================
const updatedAt = computed(() => overview.value?.updated_at || "");

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

// 全部单值指标（过滤核心指标，按数据分层展示）
const detailMetrics = computed(() => {
  const singles = overview.value?.singles || [];
  return singles.filter((s: any) => !CORE_SINGLE_SOURCES.includes(s.source));
});

// 过滤整组标灰占位（item_code === '__NA__'），仅展示有效行业
const crowdingValidItems = computed(() =>
  (crowdingItems.value || []).filter((i: any) => i.item_code !== "__NA__")
);

// ================================================================
// 方法
// ================================================================
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
  await fetchBias();
  await fetchCrowding();
  // NOTE: 与 useTemperatureOverview 各自调用一次 getTemperatureOverview，后续可合并为单一数据源
  await tempStore.fetchTemperature();
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
