<!--
  ExploreWatchlistSummaryBar · 观察列表汇总条
  从 ExploreWatchlistTable 抽出（#980 批 B5，纯搬运）。

  一行里塞了三类信息，顺序不能乱：**左边是「这页有多少东西、值多少钱」（结论）**，
  右边是「数据新不新、要不要手动刷新」（信任度）。用户先看左边，再决定要不要信右边。

  纯观察模式（未填成本份额）不显示市值 / 盈亏，改为一句说明为什么没有——
  直接藏掉那两个数字会让用户以为页面少渲染了。
-->
<template>
  <div class="summary-bar">
    <div class="summary-left">
      <span class="summary-count">共 {{ totalCount }} 项</span>
      <template v-if="!isPureObservationMode && summary">
        <span class="summary-divider">|</span>
        <span class="summary-value"
          >总市值
          <MoneyDisplay :value="summary.totalMarketValue" :show-sign="false"
        /></span>
        <span class="summary-divider">|</span>
        <span class="summary-pnl"
          >盈亏 <RiseFallText :value="summary.totalPnl" suffix=""
        /></span>
      </template>
      <span v-if="isPureObservationMode" class="summary-hint"
        >输入成本与份额后可查看持仓盈亏</span
      >
    </div>
    <div class="summary-right">
      <span class="status-indicator">
        <span class="status-dot" :class="statusClass" />{{ statusText }}
      </span>
      <el-select
        :model-value="refreshInterval"
        size="small"
        class="refresh-interval-select"
        @change="emit('interval-change', $event as number)"
      >
        <el-option
          v-for="s in REFRESH_INTERVAL_OPTIONS"
          :key="s"
          :label="`${s}s 刷新`"
          :value="s"
        />
      </el-select>
      <span v-if="lastUpdateTime" class="update-time"
        >更新: {{ formatDateTime(lastUpdateTime) }}</span
      >
      <el-button size="small" @click="emit('refresh')">刷新</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import { REFRESH_INTERVAL_OPTIONS } from "@/composables/useRealtimeQuotes";
import { formatDateTime } from "@/utils/date";

defineOptions({ name: "ExploreWatchlistSummaryBar" });

defineProps<{
  totalCount: number;
  /** true = 未填成本份额的纯观察模式（不显示市值 / 盈亏，改为一句说明） */
  isPureObservationMode: boolean;
  summary?: { totalMarketValue: number; totalPnl: number } | null;
  /** 行情状态点样式类（status-trading / status-closed / status-error / status-idle） */
  statusClass: string;
  statusText: string;
  refreshInterval: number;
  lastUpdateTime: string;
}>();

const emit = defineEmits<{
  refresh: [];
  "interval-change": [value: number];
}>();
</script>

<style lang="scss" scoped>
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.3;
  }
}

.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0 16px;

  .summary-left {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }

  .summary-count {
    font-size: var(--text-small);
    font-weight: 500;
    color: var(--text-primary);
  }

  .summary-divider {
    /* audit-text-contrast: exempt 装饰性分隔符（「/」），不承载信息、无相邻文本语义，属 WCAG 1.4.3 的 incidental；若改为信息性分隔请用 --text-tertiary-ink。登记见 docs/spec/tech-debt.md（#1599 batch 3） */
    color: var(--border-default);
  }

  .summary-value {
    font-size: var(--text-small);
    color: var(--text-secondary);
  }

  .summary-pnl {
    font-size: var(--text-small);
  }

  .summary-hint {
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  .summary-right {
    display: flex;
    gap: 12px;
    align-items: center;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  .refresh-interval-select {
    width: 96px;
  }

  .status-indicator {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;

    &.status-trading {
      background: var(--color-rise);
      animation: pulse 1.5s infinite;
    }

    &.status-closed {
      background: var(--text-tertiary);
    }

    &.status-error {
      background: var(--color-danger);
      animation: pulse 1s infinite;
    }

    &.status-idle {
      background: var(--text-disabled);
    }
  }
}
</style>
