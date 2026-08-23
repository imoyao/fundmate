<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage } from "element-plus";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import TemperatureLevelBadge from "@/components/TemperatureLevelBadge/index.vue";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { batchFetchQuotes } from "@/utils/realtimeDataSources";
import { useTemperatureOverview } from "@/composables/temperature/useTemperatureOverview";

/**
 * 探市·温度数据仪表盘（#984 explore/index.vue 拆分）。
 * 从 index.vue 原样迁移：L1 综合温度三卡 / L2 情绪+估值 / L3 流动性 /
 * 指数快照，及取数逻辑（useTemperatureOverview 为两页共用 composable）。
 */
const emit = defineEmits<{
  /** 点击综合温度卡跳转温度计 */
  "go-temperature": [];
}>();

// ================================================================
// 市场温度数据（两页共用 composable，见 #980）
// ================================================================
const {
  compositeTemperature,
  selfCalcPercent,
  selfCalcLevel,
  links,
  volumeData,
  fearData,
  jiucaishuoMediumData,
  qiemanData,
  youzhiData,
  cbTemperature,
  cbLabel,
  jisiluIndicator,
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

// 根据估值温度推断等级（PB/PE 温度越低代表估值越便宜）
const inferValuationLevel = (
  temperature: number | null | undefined
): string => {
  if (temperature == null || Number.isNaN(temperature)) return "暂无";
  if (temperature < 30) return "偏低";
  if (temperature > 70) return "偏高";
  return "适中";
};

const pbLevel = computed(() =>
  inferValuationLevel(jisiluIndicator.value?.median_pb_temperature)
);
const peLevel = computed(() =>
  inferValuationLevel(jisiluIndicator.value?.median_pe_temperature)
);

const pbCaption = computed(() => {
  const temp = jisiluIndicator.value?.median_pb_temperature;
  if (temp == null) return "估值温度 --";
  return `估值温度 ${temp}° · 越低越便宜`;
});

const peCaption = computed(() => {
  const temp = jisiluIndicator.value?.median_pe_temperature;
  if (temp == null) return "估值温度 --";
  return `估值温度 ${temp}° · 越低越便宜`;
});

// L3 深度入口
const handleShowIndustryCrowding = () => {
  ElMessage.info("行业拥挤度功能开发中");
};

const handleShowSectorFlow = () => {
  ElMessage.info("板块资金流功能开发中");
};

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
  <!-- 温度数据仪表盘                                                -->
  <!-- ============================================================ -->
  <section class="temperature-dashboard">
    <!-- 综合温度 + 恐惧贪婪 + 股债性价比（比例 2:1:1） -->
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
        @click="emit('go-temperature')"
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
          <span class="primary-link">查看温度计 ›</span>
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

    <!-- L2：市场情绪 + 估值指标（两列等宽，避免重心偏左） -->
    <div class="metrics-row">
      <!-- 市场情绪 -->
      <div class="metrics-group metrics-group--half">
        <SectionHeader title="市场情绪" />
        <MetricGrid>
          <MetricCard
            title="且慢"
            :value="qiemanData ? qiemanData.value : null"
            unit="°"
            :level="qiemanData?.label || '暂无'"
          />
          <MetricCard
            title="有知有行"
            :value="youzhiData ? youzhiData.value : null"
            unit="°"
            :level="youzhiData?.label || '暂无'"
          />
          <MetricCard
            title="韭圈儿中长期"
            :value="jiucaishuoMediumData ? jiucaishuoMediumData.value : null"
            unit="°"
            :level="jiucaishuoMediumData?.label || '暂无'"
          />
        </MetricGrid>
      </div>

      <!-- 估值指标 -->
      <div class="metrics-group metrics-group--half">
        <SectionHeader title="估值指标" />
        <MetricGrid>
          <MetricCard
            title="中位PB"
            :value="jisiluIndicator?.median_pb ?? null"
            unit="倍"
            :level="pbLevel"
            :caption="pbCaption"
          />
          <MetricCard
            title="中位PE"
            :value="jisiluIndicator?.median_pe ?? null"
            unit="倍"
            :level="peLevel"
            :caption="peCaption"
          />
          <MetricCard
            title="可转债"
            :value="cbTemperature != null ? cbTemperature : null"
            unit="°"
            :level="cbLabel || '暂无'"
          />
        </MetricGrid>
      </div>
    </div>

    <!-- L3：流动性（独占一行，横向大卡片，信息更聚焦） -->
    <div class="metrics-row metrics-row--single">
      <div class="liquidity-block">
        <SectionHeader title="流动性" />
        <div class="liquidity-card">
          <div class="liquidity-metric">
            <span class="liquidity-metric__label">今日成交额</span>
            <div class="liquidity-metric__body">
              <span class="liquidity-metric__value">{{
                volumeData ? volumeData.value : "--"
              }}</span>
              <span class="liquidity-metric__unit">亿</span>
              <TemperatureLevelBadge
                :level="volumeData?.label || '暂无'"
                size="sm"
              />
            </div>
            <span class="liquidity-metric__hint">成交量热度反映市场活跃度</span>
          </div>
          <div class="liquidity-divider" />
          <div class="liquidity-actions">
            <el-button
              link
              class="liquidity-btn"
              @click="handleShowIndustryCrowding"
              >行业拥挤度 →</el-button
            >
            <el-button link class="liquidity-btn" @click="handleShowSectorFlow"
              >板块资金流 →</el-button
            >
          </div>
        </div>
      </div>
    </div>

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


/* ============================================================
   响应式（仪表盘相关部分）
   ============================================================ */
@media (width <= 1024px) {
  .metrics-row {
    grid-template-columns: 1fr;
  }

  .liquidity-card {
    flex-direction: row;
    gap: 20px;
    align-items: center;
  }

  .liquidity-divider {
    width: 1px;
    height: 64px;
  }
}

@media (width <= 768px) {
  .temperature-dashboard {
    padding: 0 16px 12px;
  }

  .snapshot-items {
    gap: 12px;
  }

  .liquidity-card {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .liquidity-metric {
    align-items: center;
    text-align: center;
  }

  .liquidity-divider {
    width: auto;
    height: 1px;
  }

  .liquidity-actions {
    flex-direction: row;
    justify-content: center;
  }
}

@media (width <= 480px) {
  .liquidity-metric__value {
    font-size: 28px;
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

/* 探市「综合温度」卡内的进度条与跳转提示（来自 TemperatureGaugeCard 的 footer 插槽，属父组件作用域） */
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

/* ---- 分组指标区：情绪/估值两列等宽，流动性独占一行 ---- */
.metrics-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 16px;

  &--single {
    grid-template-columns: 1fr;
  }
}

.metrics-group {
  padding: 16px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.liquidity-block {
  display: flex;
  flex-direction: column;
  padding: 16px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.liquidity-card {
  display: flex;
  flex-direction: row;
  gap: 24px;
  align-items: center;
  justify-content: space-between;
  padding: 8px 4px;
  margin-top: 4px;
}

.liquidity-metric {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
  text-align: left;

  &__label {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-secondary);
  }

  &__body {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: baseline;
  }

  &__value {
    font-family: var(--font-mono);
    font-size: 42px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    color: var(--text-primary);
  }

  &__unit {
    font-size: 16px;
    font-weight: 500;
    color: var(--text-secondary);
  }

  &__hint {
    font-size: 12px;
    color: var(--text-tertiary);
  }
}

.liquidity-divider {
  flex-shrink: 0;
  width: 1px;
  height: 64px;
  background: var(--border-light);
}

.liquidity-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 120px;
}

.liquidity-btn {
  justify-content: flex-start;
  padding: 0;
  font-size: 13px;
  color: var(--text-secondary);

  &:hover {
    color: var(--brand-700);
  }
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

/* ============================================================
   温度仪表盘样式（自 index.vue 随组件迁移，#984）
   ============================================================ */
</style>
