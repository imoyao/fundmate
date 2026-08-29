<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { formatQuantity } from "@/utils/format";
import type { AggregationProductGroup } from "@/api/ledger";

/**
 * 聚合视图产品卡片（#1101 / #1132 共用）。
 *
 * 范式由 el-table 表格改为卡片（#1133）：信息分层更清晰、扫描式浏览更友好，
 * 与截图原型「持有份额 / 参考净值 / 资产情况」三列指标一致。
 * 产品名单行截断 + title 兜底，避免长基金名撑破布局。
 */
defineOptions({ name: "AggregationProductCard" });

const props = defineProps<{
  group: AggregationProductGroup;
}>();

const emit = defineEmits<{
  (e: "select", group: AggregationProductGroup): void;
}>();

/** 最小单位（份×10000）→ 可读份额（份） */
const shares = computed(() => (props.group.quantity || 0) / 10000);
/** 市值（分）→ 元 */
const marketValueYuan = computed(
  () => (props.group.market_value_cents || 0) / 100
);
/** 参考净值（元）；无快照/未同步时为 null */
const nav = computed(() => props.group.nav_yuan ?? null);
</script>

<template>
  <div
    class="product-card"
    role="button"
    tabindex="0"
    @click="emit('select', group)"
    @keydown.enter="emit('select', group)"
  >
    <div class="card-head">
      <p class="product-name" :title="group.name || ''">
        {{ group.name || "--" }}
      </p>
      <p class="product-sub">
        <span class="product-code">{{ group.symbol }}</span>
        <template v-if="group.fund_manager">
          <span class="sub-dot">·</span>
          <span class="product-manager">{{ group.fund_manager }}</span>
        </template>
      </p>
    </div>

    <div class="metric-row">
      <div class="metric">
        <span class="metric-label">持有份额</span>
        <span class="metric-value">{{ formatQuantity(shares) }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">参考净值</span>
        <span class="metric-value">{{
          nav != null ? nav.toFixed(4) : "--"
        }}</span>
      </div>
      <div class="metric metric--amount">
        <span class="metric-label">资产情况</span>
        <MoneyDisplay
          :value="marketValueYuan"
          size="md"
          :show-sign="false"
          :auto-color="false"
        />
      </div>
    </div>

    <div v-if="group.sources.length > 1" class="card-foot">
      <IconifyIconOffline icon="ep:office-building" class="foot-icon" />
      <span>{{ group.sources.length }} 个账户持有</span>
    </div>
  </div>
</template>

<style scoped>
@media (width <= 520px) {
  .metric-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    row-gap: 12px;
  }

  .metric--amount {
    grid-column: span 2;
  }
}

@media (prefers-reduced-motion: reduce) {
  .product-card {
    transition: none;
  }

  .product-card:hover {
    transform: none;
  }
}

.product-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-4, 16px);
  padding: var(--space-standard, 18px);

  /* 数字等宽：消除份额/净值/金额的宽度抖动 */
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  transition:
    box-shadow 0.2s ease,
    transform 0.2s ease,
    border-color 0.2s ease;
}

.product-card:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-overlay, var(--shadow-raised));
  transform: translateY(-2px);
}

.product-card:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.card-head {
  min-width: 0;
}

/* 单行截断：与 ProductDisplay 的 product-name 规范一致 */
.product-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.product-sub {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.product-code {
  font-family: var(--font-mono);
  letter-spacing: 0.02em;
}

.sub-dot {
  opacity: 0.6;
}

.product-manager {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3, 12px);
  padding-top: var(--space-3, 12px);
  border-top: 1px solid var(--border-subtle, var(--border-light));
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.metric--amount {
  align-items: flex-end;
  text-align: right;
}

.metric-label {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.metric-value {
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.card-foot {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
  color: var(--text-tertiary);
}

.foot-icon {
  font-size: 12px;
}
</style>
