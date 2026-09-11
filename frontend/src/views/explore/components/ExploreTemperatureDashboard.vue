<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import { batchFetchQuotes } from "@/utils/realtimeDataSources";
import { useTemperatureOverview } from "@/composables/temperature/useTemperatureOverview";

/**
 * 探市·概览档温度锚点（#984 拆分；2026-09-12 方案 D 精简）。
 *
 * 精简理由：原 L2（市场情绪 / 估值指标）与 L3（流动性）各卡，在「深度」档
 * （ExploreDetailPanel 的 coreMetrics 与 MetricDetailTable）已有更完整的同源呈现，
 * 留在概览档属于重复。概览档只保留一屏可读的温度锚点 + 指数快照，
 * 把版面让给观察列表（漏斗主体）。
 *
 * 详情去向：可转债/成交额 → 深度档 coreMetrics；且慢/有知有行/韭圈儿/中位PB/中位PE
 *          → 深度档 MetricDetailTable。
 */
const emit = defineEmits<{
  /** 点击综合温度卡：切换到父页面的「深度」档 */
  "go-detail": [];
}>();

// ================================================================
// 市场温度数据（两页共用 composable，见 #980）
// ================================================================
const {
  compositeTemperature,
  selfCalcPercent,
  selfCalcLevel,
  links,
  fearData,
  fetchTemperature
} = useTemperatureOverview();

/** links 暴露给父页面：底部 footer 的数据来源列表依赖它 */
defineExpose({ links });

// 综合温度进度条颜色：按温度档位取色，偏低时为绿色
const progressColor = computed(() => {
  const v = compositeTemperature.value?.value;
  if (v == null || Number.isNaN(v)) return "var(--temp-mid)";
  if (v < 40) return "var(--temp-low)";
  if (v > 60) return "var(--temp-high)";
  return "var(--temp-mid)";
});

// ================================================================
// 指数快照
// ================================================================
interface IndexInfo {
  code: string;
  name: string;
  price: number | null;
  changePercent: number;
}

const indexCodes = [
  { symbol: "000300", type: "stock" as const },
  { symbol: "000905", type: "stock" as const },
  { symbol: "399006", type: "stock" as const }
];

const indexData = ref<IndexInfo[]>([
  { code: "000300", name: "沪深300", price: null, changePercent: 0 },
  { code: "000905", name: "中证500", price: null, changePercent: 0 },
  { code: "399006", name: "创业板指", price: null, changePercent: 0 }
]);

const indexLoading = ref(false);

const fetchIndexData = async () => {
  indexLoading.value = true;
  try {
    const result = await batchFetchQuotes(indexCodes);
    indexData.value = indexData.value.map(idx => {
      const quote = result.get(idx.code);
      if (quote) {
        const price = quote.currentPrice || 0;
        const change = quote.changePct || 0;
        return {
          ...idx,
          price: price > 0 ? price : null,
          changePercent: change
        };
      }
      return idx;
    });
  } catch {
    // 静默失败
  } finally {
    indexLoading.value = false;
  }
};

onMounted(() => {
  fetchTemperature();
  fetchIndexData();
});
</script>

<template>
  <!-- ============================================================ -->
  <!-- 温度锚点：综合温度 + 恐惧贪婪 + 股债性价比（一屏一行）        -->
  <!-- ============================================================ -->
  <section class="temperature-dashboard">
    <MetricGrid>
      <!-- 综合温度 -->
      <TemperatureGaugeCard
        class="gauge-card--featured"
        :value="compositeTemperature?.value ?? null"
        title="综合温度"
        :level="compositeTemperature?.level || '暂无'"
        caption="综合6个市场指标"
        size="sm"
        clickable
        @click="emit('go-detail')"
      >
        <template #footer>
          <div class="primary-bar">
            <div
              class="primary-fill"
              :style="{
                width:
                  (compositeTemperature?.value != null
                    ? Math.max(0, Math.min(100, compositeTemperature.value))
                    : 0) + '%',
                background: progressColor
              }"
            />
          </div>
          <span class="primary-link">查看详细温度 ›</span>
        </template>
      </TemperatureGaugeCard>

      <!-- 恐惧贪婪 -->
      <MetricCard
        title="恐惧贪婪"
        :value="fearData ? fearData.value : null"
        :level="fearData?.label || '暂无数据'"
      />

      <!-- 股债性价比 -->
      <MetricCard
        title="股债性价比"
        :value="selfCalcPercent != null ? selfCalcPercent : null"
        unit="%"
        :level="selfCalcLevel"
      />
    </MetricGrid>

    <!-- 指数快照（独立一行） -->
    <div class="index-snapshot">
      <div class="snapshot-title">指数快照</div>
      <div class="snapshot-items">
        <div v-for="idx in indexData" :key="idx.code" class="snapshot-item">
          <span class="snapshot-name">{{ idx.name }}</span>
          <span v-if="idx.price === null" class="snapshot-price">--</span>
          <MoneyDisplay v-else :value="idx.price" :precision="2" />
          <span class="snapshot-change"
            ><RiseFallText :value="idx.changePercent"
          /></span>
        </div>
      </div>
    </div>
  </section>
</template>

<style lang="scss" scoped>
@media (width <= 768px) {
  .temperature-dashboard {
    padding: 0 16px 12px;
  }

  .snapshot-items {
    gap: 12px;
  }
}

.temperature-dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1280px;
  padding: var(--space-standard) 24px 16px;
  margin: 0 auto;
}

/* 「综合温度」卡内的进度条与跳转提示（来自 TemperatureGaugeCard 的 footer 插槽） */
.primary-bar {
  height: 3px;
  overflow: hidden;
  background: var(--bg-soft);
  border-radius: 2px;
}

.primary-fill {
  height: 100%;
  border-radius: 2px;
  transition:
    width 0.8s ease,
    background 0.6s ease;
}

.primary-link {
  display: inline-block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-primary);
  white-space: nowrap;
  cursor: pointer;
}

/* ---- 指数快照 ---- */
.index-snapshot {
  padding: 16px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.snapshot-title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.snapshot-items {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
}

.snapshot-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.snapshot-name {
  font-size: 13px;
  color: var(--text-secondary);
}

.snapshot-price {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.snapshot-change {
  font-size: 13px;
}
</style>
