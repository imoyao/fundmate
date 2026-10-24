<script setup lang="ts">
// 账户卡片的核心指标区：总资产（左，大号锚点）+ 当日盈亏 / 持仓盈亏（右，竖排）。
//
// 多根片段（`div.ledger-metrics` + 条件渲染的 `div.ledger-liability`），不包 wrapper——
// 它们在 `.ledger-card` 里本来就是并列的直接子元素，包一层会让卡片内边距多作用一级。
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import {
  hasLinkedLiability,
  pnlLabelOf,
  pnlMetricKindOf
} from "./ledgerCardModel";

defineProps<{ ledger: any }>();
</script>

<template>
  <!-- 核心指标：左右两列 flex（总资产为左侧大数字锚点，右侧两指标独立竖排，
       避免大数字撑高整行把右侧指标挤到下方） -->
  <div class="ledger-metrics">
    <div class="metric metric--main">
      <span class="metric-label" :style="{ color: 'var(--text-tertiary-ink)' }"
        >总资产</span
      >
      <span class="metric-value" :style="{ color: 'var(--text-primary)' }">
        <MoneyDisplay
          :value="ledger.total_market_value || 0"
          :show-sign="false"
          :auto-color="false"
          size="lg"
        />
      </span>
    </div>
    <!-- 右侧两指标：独立竖排容器，垂直居中于卡片高度，互不挤压 -->
    <div class="metric-side">
      <!-- 当日盈亏：暂无当日行情数据，保留占位符 -->
      <div class="metric">
        <span
          class="metric-label"
          :style="{ color: 'var(--text-tertiary-ink)' }"
          >当日盈亏</span
        >
        <span
          class="metric-value"
          :style="{ color: 'var(--text-tertiary-ink)' }"
          >--</span
        >
      </div>
      <!-- 持仓盈亏：银行显示活期余额、实物显示估值项数 -->
      <div class="metric">
        <span
          class="metric-label"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          {{ pnlLabelOf(ledger.ledger_type) }}
        </span>
        <span
          v-if="pnlMetricKindOf(ledger) === 'cash'"
          class="metric-value"
          :style="{ color: 'var(--text-secondary)' }"
        >
          <MoneyDisplay
            :value="ledger.cash_balance"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </span>
        <span
          v-else-if="pnlMetricKindOf(ledger) === 'count'"
          class="metric-value"
          :style="{ color: 'var(--text-secondary)' }"
        >
          {{ ledger.position_count || 0 }} 项
        </span>
        <span v-else class="metric-value">
          <!-- 盈亏数字走 MoneyDisplay 自动涨红跌绿 -->
          <MoneyDisplay :value="ledger.pnl || 0" size="sm" />
        </span>
      </div>
    </div>
  </div>

  <!-- 关联负债（仅银行账户且存在房贷时显示；负债属中性信息，用 text-secondary） -->
  <div v-if="hasLinkedLiability(ledger)" class="ledger-liability">
    <span class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }"
      >关联负债</span
    >
    <span
      class="text-xs font-medium"
      :style="{ color: 'var(--text-secondary)' }"
    >
      <MoneyDisplay
        :value="-ledger.linked_liability"
        :auto-color="false"
        size="xs"
      />
    </span>
  </div>
</template>

<style scoped>
/* ===== 核心指标：左右两列 flex（总资产大数字锚点 + 右侧两指标独立竖排） ===== */
.ledger-metrics {
  display: flex;
  gap: var(--space-3);
  align-items: stretch;
}

.metric--main {
  display: flex;
  flex: 1.25;
  flex-direction: column;
  gap: 2px;
  justify-content: center;
  min-width: 0;
  overflow-wrap: anywhere;
}

.metric-side {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-2);
  justify-content: center;
  min-width: 0;
}

.metric-label {
  display: block;
  font-size: var(--text-label, 13px);
  line-height: 18px;
}

.metric-value {
  display: block;
  font-size: var(--text-small, 14px);
  font-variant-numeric: tabular-nums;
  line-height: 22px;
}

.ledger-liability {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-2);
  margin-top: var(--space-3);
  font-variant-numeric: tabular-nums;
  border-top: 1px solid var(--border-subtle);
}
</style>
