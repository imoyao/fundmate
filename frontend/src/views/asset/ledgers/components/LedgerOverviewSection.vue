<template>
  <!-- 顶部双卡：净资产卡 + 资产配置环形图（md 两列并排，等高） -->
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
    <!-- 净资产卡：左侧大数字锚点，右侧指标区竖排（总资产/负债/负债率） -->
    <div class="overview-card net-worth-card">
      <div class="flex justify-between gap-6 flex-1 items-center">
        <div class="min-w-0">
          <p class="text-sm" :style="{ color: 'var(--text-tertiary-ink)' }">
            净资产
          </p>
          <p class="mt-1">
            <MoneyDisplay :value="p.overviewData.net_worth" size="xl" />
          </p>
          <!-- 负债率偏高：警示态才用系统危险色（非涨跌色），放在大数字下方 -->
          <div
            v-if="p.showHighLiabilityWarning"
            class="liability-warning-badge mt-3"
          >
            负债率偏高
          </div>
        </div>
        <!-- 右侧指标区：三指标竖排，label 上数值下，--border-subtle 细分隔 -->
        <div class="overview-metrics">
          <div class="metric-item">
            <span class="metric-label">总资产</span>
            <MoneyDisplay
              :value="p.totalAssets"
              :show-sign="false"
              :auto-color="false"
              size="sm"
            />
          </div>
          <!-- 负债为 0 时不渲染负债信息位，保持摘要干净；
                   负债金额属中性财务信息，用 text-secondary，不用涨跌色误导 -->
          <div v-if="p.overviewData.liability_total > 0" class="metric-item">
            <span class="metric-label">负债</span>
            <MoneyDisplay
              :value="p.overviewData.liability_total"
              :show-sign="false"
              :auto-color="false"
              size="sm"
            />
          </div>
          <div class="metric-item">
            <span class="metric-label">负债率</span>
            <!-- 可计算时显示百分比，无负债或不可计算显示 --；浅灰胶囊弱化中性信息 -->
            <span class="liability-rate-pill">{{ p.liabilityRate }}</span>
          </div>
        </div>
      </div>
      <!-- 更新时间：右上角 -->
      <div class="hidden md:block text-right mt-4">
        <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
          更新于 {{ p.lastUpdate }}
        </p>
      </div>
    </div>
    <!-- 资产配置环形图卡（#984 拆分至 components/LedgerAllocationCard.vue） -->
    <LedgerAllocationCard
      :groups="p.overviewData?.groups ?? []"
      :total-assets="p.totalAssets"
    />
  </div>

  <!-- 聚合汇总卡网格：场外基金 / 场内证券 两卡并排（窄屏单列堆叠），等高等高权重 -->
  <div class="aggregation-cards-grid mb-6">
    <!-- 场外基金（含E账户）聚合汇总卡：整卡可点下钻至聚合视图 -->
    <div
      class="overview-card fund-summary-card"
      role="button"
      tabindex="0"
      @click="p.goToFundAggregation"
      @keydown.enter="p.goToFundAggregation"
    >
      <div class="flex justify-between items-center gap-4 flex-wrap">
        <div class="min-w-0">
          <p class="text-sm" :style="{ color: 'var(--text-tertiary-ink)' }">
            基金
          </p>
          <div class="mt-1">
            <MoneyDisplay
              :value="p.fundTotalYuan"
              size="lg"
              :show-sign="false"
              :auto-color="false"
            />
          </div>
        </div>
        <el-button type="primary" plain @click.stop="p.goToFundAggregation">
          <IconifyIconOffline icon="ep:right" class="mr-1" /> 查看明细
        </el-button>
      </div>
    </div>

    <!-- 场内证券（股票/ETF/可转债）聚合汇总卡：整卡可点下钻至聚合视图 -->
    <div
      class="overview-card securities-summary-card"
      role="button"
      tabindex="0"
      @click="p.goToSecuritiesAggregation"
      @keydown.enter="p.goToSecuritiesAggregation"
    >
      <div class="flex justify-between items-center gap-4 flex-wrap">
        <div class="min-w-0">
          <p class="text-sm" :style="{ color: 'var(--text-tertiary-ink)' }">
            股票
          </p>
          <div class="mt-1">
            <MoneyDisplay
              :value="p.securitiesTotalYuan"
              size="lg"
              :show-sign="false"
              :auto-color="false"
            />
          </div>
        </div>
        <el-button
          type="primary"
          plain
          @click.stop="p.goToSecuritiesAggregation"
        >
          <IconifyIconOffline icon="ep:right" class="mr-1" /> 查看明细
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import LedgerAllocationCard from "./LedgerAllocationCard.vue";
import type { useLedgerList } from "../composables/useLedgerList";

defineOptions({ name: "LedgerOverviewSection" });

/**
 * 账户列表页顶部汇总区（#980 P1-C 结构拆分）：
 * 净资产卡（指标竖排/负债警示）+ 资产配置环形图 + 基金/证券聚合汇总卡。
 * page 为 index 注入的状态单体；p 用 reactive 解包，使模板表达式与拆分前逐字一致。
 */
const props = defineProps<{ page: ReturnType<typeof useLedgerList> }>();
const p = reactive(props.page);
</script>

<style scoped>
/* 尊重系统减弱动效偏好：本组件承载的卡片 hover 效果关闭
   （自 index 原整块按选择器拆分，其余规则见各组件 scoped 块） */
@media (prefers-reduced-motion: reduce) {
  .overview-card {
    transition: none;
  }

  /* 聚合卡 hover 上浮同样尊重减弱动效偏好 */
  .fund-summary-card:hover,
  .securities-summary-card:hover {
    transform: none;
  }
}

/* ===== 全局汇总卡片（--space-standard 间距，净资产大数字锚点） =====
   卡片统一使用 --card-border 描边（design.md / design.dark.md 规范：卡片边框必须用 --card-border），
   hover 用 translateY 浮起 + 浮起阴影（见下方聚合卡）。 */
.overview-card {
  padding: var(--space-standard);
  background: var(--bg-card);
  border: var(--card-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

/* 净资产卡：纵向布局，更新时间贴底，与右侧图表卡等高对齐 */
.net-worth-card {
  display: flex;
  flex-direction: column;
}

/* 场外基金（含E账户）汇总卡：整卡可点下钻，复用 overview-card 视觉语言。
   hover 与账户卡片（LedgerCard）统一为「上浮 + 浮起阴影」，边框由 --card-border 统一提供，hover 不改 border-color。 */
.fund-summary-card {
  cursor: pointer;
  transition:
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.fund-summary-card:hover {
  box-shadow: var(--shadow-float);
  transform: translateY(-2px);
}

.fund-summary-card:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

/* 场内证券（股票/ETF/可转债）汇总卡：整卡可点下钻，复用 fund-summary-card 视觉语言。
   hover 与账户卡片（LedgerCard）统一为「上浮 + 浮起阴影」，边框由 --card-border 统一提供，hover 不改 border-color。 */
.securities-summary-card {
  cursor: pointer;
  transition:
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.securities-summary-card:hover {
  box-shadow: var(--shadow-float);
  transform: translateY(-2px);
}

.securities-summary-card:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

/* 聚合汇总卡网格：场外基金 / 场内证券 两卡并排，等宽等高（grid 默认 align-items: stretch）；
   minmax(0, 1fr) 防止金额等超长内容撑破列宽；窄屏（<768px，与 Tailwind md 断点对齐）回退单列堆叠 */
.aggregation-cards-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-compact);
}

@media (width <= 767px) /* breakpoint-allow: 拆分随迁的存量写法，零变更不改输出 */ {
  .aggregation-cards-grid {
    grid-template-columns: 1fr;
  }
}

/* 负债率偏高警示：负债属中性信息，警示态才用系统危险色（非涨跌色） */
.liability-warning-badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  line-height: 18px;
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
  border-radius: var(--radius-pill);
}

/* ===== 净资产卡右侧指标区：三指标竖排，label 上数值下，--border-subtle 细分隔 ===== */
.overview-metrics {
  display: flex;
  flex-direction: column;

  /* 间距 12px -> 16px：--space-4 未定义（见 profile/index.vue 前车之鉴），用 --space-compact */
  gap: var(--space-compact);
  min-width: 160px;

  /* 数字等宽对齐：消除金额宽度抖动 */
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 2px;

  /* 子元素统一右对齐：label/数值/胶囊与整体 text-align 一致，消除「对齐奇怪」 */
  align-items: flex-end;
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-subtle);
}

.metric-item:first-child {
  padding-top: 0;
  border-top: none;
}

/* 指标区 label：限定在 overview-metrics 内，避免与账户卡片的 .metric-label 混淆 */
.overview-metrics .metric-label {
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-tertiary-ink);
}

/* 负债率胶囊：--bg-soft 底 + --radius-pill + --text-tertiary 字，弱化中性信息。
   右对齐由 .metric-item 的 align-items: flex-end 统一提供，不再单独 align-self */
.liability-rate-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  padding: 1px 10px;
  font-size: var(--text-label, 13px);
  line-height: 20px;
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}
</style>
