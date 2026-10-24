<script setup lang="ts">
// 「深度」档的仪表盘 + 温度解读 + 市场机会（原 ExploreDetailPanel 的上半屏）。
//
// 两段是**并列的两个 <section>**（多根片段，不额外包 div）：它们在父容器里是直接子元素，
// 抽出来时若包一层 wrapper，`.detail-panel` 的间距规则会多作用一层，页面结构也就变了。
//
// 数据来自单例 composable（与概览档共享同一份实例，见 useTemperatureOverview 头注释），
// 故这里自己取，不用父层传 10 个 prop。
import { computed } from "vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import TemperatureContextCard from "@/components/TemperatureContextCard/index.vue";
import { useTemperatureOverview } from "@/composables/temperature/useTemperatureOverview";
import { useCoreMetrics } from "@/composables/temperature/useCoreMetrics";

withDefaults(
  defineProps<{
    /**
     * 是否渲染「综合温度」仪表盘。
     * 父页面按当前档位传入：深度档显示时 true、概览档 false ——
     * 概览档已有一份同源同貌的温度计卡，两份同时留在 DOM 中属重复（#1549 T4.1）。
     * 仪表卡自身不取数（数据来自单例 composable），卸载重挂不会多打接口。
     */
    gaugeVisible?: boolean;
  }>(),
  { gaugeVisible: true }
);

const { loading, overview, compositeTemperature, fearData } =
  useTemperatureOverview();

// 核心指标清单收口在 useCoreMetrics（见 #980）
const { coreMetrics } = useCoreMetrics();

const updatedAt = computed(() => overview.value?.updated_at || "");

const compositeValue = computed(
  () => compositeTemperature.value?.value ?? null
);

// 等级文案与概览档同源同文案（含「暂无」兜底）：缺数据时不能兜成 TemperatureLevelBadge
// 的默认「适中」——那会在无数据时给出「市场平稳」的错误结论（#1549 T4.1）。
const compositeLevel = computed(
  () => compositeTemperature.value?.level || "暂无"
);

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

// ================================================================
// 市场机会清单（B3：后端 insights 归集，前端只映射 tone→样式）
// #1546 T2.1：直接由总览响应派生，**不再经 temperature store 重复打一次**
// /api/temperature/overview（原实现是 composable 与 store 各拉一遍同一接口）
// ================================================================
const opportunityList = computed(() =>
  (overview.value?.insights ?? []).map(i => ({
    name: i.name,
    desc: i.desc,
    tone: i.tone
  }))
);
</script>

<template>
  <!-- 综合仪表盘 -->
  <section v-loading="loading" class="dashboard-section">
    <MetricGrid>
      <!-- 综合温度仪表（大）——与概览档同源同貌；gaugeVisible 保证同一时刻
           全页只有一份仪表盘在 DOM 中（#1549 T4.1，参数由 index.vue 按档位传入） -->
      <TemperatureGaugeCard
        v-if="gaugeVisible"
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
      <CardBlock v-if="opportunityList.length" class="opportunity-card">
        <SectionHeader title="市场机会" />
        <div class="opportunity-list">
          <div
            v-for="op in opportunityList"
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
      </CardBlock>
    </div>
  </section>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

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

  /* 窄屏「温度解读 + 市场机会」由并排改单列。
     同 `padding` 那条：必须留在基础声明之后，否则会被 `grid-template-columns: 1.6fr 1fr` 压掉
     （2026-09-18 之前是「960px 及以下」的裸查询且排在前面，从未生效）。
     断点按 Tailwind 单一来源取 `lg`（<1024px；原数值 960px 随断点对齐外移）。 */
  @include bp.below("lg") {
    grid-template-columns: 1fr;
  }
}

/* TemperatureContextCard 自带卡片外壳（--bg-card / --border-light / --radius-lg /
   --shadow-raised），父级此处只补裁切，不再重复声明外壳（#1547 T3.1）。 */
.context-card {
  overflow: hidden;
}

/* 区块外壳统一走 CardBlock（#1547 T3.1 收敛），此处只留内部排布 */
.opportunity-card {
  display: flex;
  flex-direction: column;
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
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.opportunity-tag {
  padding: 2px 8px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  white-space: nowrap;
  background: var(--border-light);
  border-radius: 10px;
}

.opportunity-item--safe .opportunity-tag {
  color: var(--temp-low-ink);
  background: color-mix(in srgb, var(--temp-low) 18%, transparent);
}

.opportunity-item--danger .opportunity-tag {
  color: var(--temp-high-ink);
  background: color-mix(in srgb, var(--temp-high) 18%, transparent);
}

.opportunity-desc {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-secondary);
}
</style>
