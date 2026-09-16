<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import { batchFetchQuotes } from "@/utils/realtimeDataSources";
import { useTemperatureOverview } from "@/composables/temperature/useTemperatureOverview";
import { useCoreMetrics } from "@/composables/temperature/useCoreMetrics";

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

/**
 * 是否渲染温度计卡。父页面按当前档位传入：概览档显示时=true、深度档=false。
 * 目的只有一个 —— 同一时刻全页只留一份温度仪表盘在 DOM 中（#1549 T4.1）。
 * 卡片本身不取数（数据来自单例 composable），卸载重挂不会产生额外请求。
 */
withDefaults(
  defineProps<{
    gaugeVisible?: boolean;
  }>(),
  { gaugeVisible: true }
);

// ================================================================
// 市场温度数据（两页共用 composable，见 #980）
// ================================================================
const { compositeTemperature, freshness, fetchTemperature } =
  useTemperatureOverview();

// 核心指标清单收口在 useCoreMetrics（见 #980）：两档不再各写一遍指标映射
const { overviewMetrics } = useCoreMetrics();

// 说明：数据来源链接（links）现由父页面直接从 useTemperatureOverview 读取，
// 本组件不再 defineExpose —— 避免 footer 依赖概览档组件的挂载状态。

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
    <!-- 数据新鲜度守卫（#1431）：最新数据超阈值未更新时显式提示，不静默展示旧值 -->
    <div v-if="freshness?.stale" class="freshness-alert" role="alert">
      <IconifyIconOffline icon="ep:warning" class="freshness-alert__icon" />
      <span class="freshness-alert__text">
        当前展示的是 {{ freshness.latest || "更早" }} 的市场数据（距今约
        {{ freshness.age_days }} 天，已超过 {{ freshness.threshold_days }}
        天阈值），数据源可能暂不可用，请谨慎参考。
      </span>
    </div>

    <MetricGrid>
      <!-- 综合温度锚点 -->
      <!-- 尺寸/外观（lg + featured）与标题/副标题/等级文案全部与深度档对齐，
           禁止再手拼 class="gauge-card--featured" 旁路 —— 两档必须是逐字同一张卡，
           否则切档时卡片会跳变（#1549 T4.1）。
           gaugeVisible：只让当前档那份仪表盘留在 DOM 里，避免同一张英雄卡出现两份。 -->
      <TemperatureGaugeCard
        v-if="gaugeVisible"
        :value="compositeTemperature?.value ?? null"
        title="综合市场温度"
        :level="compositeTemperature?.level || '暂无'"
        caption="基于多源市场数据计算"
        size="lg"
        featured
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

      <!-- 核心锚点指标（恐惧贪婪 / 股债性价比）：清单定义见 useCoreMetrics -->
      <MetricCard
        v-for="metric in overviewMetrics"
        :key="metric.key"
        :title="metric.title"
        :value="metric.value"
        :unit="metric.unit"
        :level="metric.level"
      />
    </MetricGrid>

    <!-- 指数快照（独立一行）：容器改走 CardBlock（#1549 T3.1），
         内部改真表格（#1549 T4.2）——原裸 flex 下指数名长度不同，
         三个数值不成列、换行后更错位。 -->
    <CardBlock class="index-snapshot">
      <div class="snapshot-title">指数快照</div>
      <table class="snapshot-table">
        <tbody>
          <tr v-for="idx in indexData" :key="idx.code">
            <th scope="row" class="snapshot-name">{{ idx.name }}</th>
            <td class="snapshot-price">
              <span v-if="idx.price === null">--</span>
              <MoneyDisplay v-else :value="idx.price" :precision="2" />
            </td>
            <td class="snapshot-change">
              <RiseFallText :value="idx.changePercent" />
            </td>
          </tr>
        </tbody>
      </table>
    </CardBlock>
  </section>
</template>

<style lang="scss" scoped>
/* 数据新鲜度守卫横幅（#1431）：沿用「数据滞后」pill 的警示色视觉语言 */
.freshness-alert {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: color-mix(
    in srgb,
    var(--color-warning, #d97706) 12%,
    transparent
  );
  border: 1px solid
    color-mix(in srgb, var(--color-warning, #d97706) 35%, transparent);
  border-radius: 8px;
}

.freshness-alert__icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.freshness-alert__text {
  flex: 1;
}

@media (width <= 768px) {
  .temperature-dashboard {
    padding: 0 16px 12px;
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

/* ---- 指数快照 ----
   卡片外观（bg-card / border-light / radius-lg / shadow-raised / padding）
   统一由 CardBlock 承载，本类不再自定义外壳。 */
.snapshot-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

/* 真表格：三行共用同一组列宽 + 数值列右对齐 + 等宽数字
   → 三个数值严格成列，修掉「指数名长度不同导致数值不对齐」（#1549 T4.2） */
.snapshot-table {
  width: 100%;
  max-width: 420px;
  border-collapse: collapse;

  th,
  td {
    padding: 5px 0;
    font-size: 14px;
    line-height: 1.5;
    vertical-align: baseline;
  }
}

.snapshot-name {
  font-weight: 400;
  color: var(--text-secondary);
  text-align: left;
}

.snapshot-price,
.snapshot-change {
  text-align: right;
  white-space: nowrap;
}

.snapshot-price {
  width: 120px;
  font-family: var(--font-mono);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.snapshot-change {
  width: 88px;
  font-size: 13px;
}
</style>
