<script setup lang="ts">
import { computed, ref } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { formatQuantity } from "@/utils/format";
import type { AggregationInstitutionGroup } from "@/api/ledger";

/**
 * 聚合视图机构分组卡（#1101 / #1132 共用）。
 *
 * 「按机构」维度下按销售机构聚合，点击展开该机构下的持仓明细。
 * 机构中文名由后端 join AMAC 名录直接给出，前端**不再**拼「销售机构 #id」占位文案（#1133）。
 */
defineOptions({ name: "AggregationInstitutionCard" });

const props = defineProps<{
  group: AggregationInstitutionGroup;
}>();

const expanded = ref(false);
const marketValueYuan = computed(
  () => (props.group.market_value_cents || 0) / 100
);
const itemCount = computed(() => props.group.items.length);

function toggle() {
  expanded.value = !expanded.value;
}
</script>

<template>
  <div class="institution-card">
    <div
      class="card-head"
      role="button"
      tabindex="0"
      :aria-expanded="expanded"
      @click="toggle"
      @keydown.enter="toggle"
    >
      <div class="head-left">
        <p class="institution-name" :title="group.institution_name">
          {{ group.institution_name }}
        </p>
        <p class="institution-sub">{{ itemCount }} 项持仓</p>
      </div>
      <div class="head-right">
        <MoneyDisplay
          :value="marketValueYuan"
          size="md"
          :show-sign="false"
          :auto-color="false"
        />
        <IconifyIconOffline
          icon="ep:arrow-down"
          class="expand-icon"
          :class="{ 'is-expanded': expanded }"
        />
      </div>
    </div>

    <div v-if="expanded" class="item-list">
      <div
        v-for="(item, idx) in group.items"
        :key="`${item.ledger_id}-${item.symbol}-${idx}`"
        class="item-row"
      >
        <div class="item-main">
          <span class="item-name" :title="item.name || ''">{{
            item.name || "--"
          }}</span>
          <span class="item-code">{{ item.symbol }}</span>
        </div>
        <div class="item-metrics">
          <span class="item-shares">{{
            formatQuantity((item.quantity || 0) / 10000)
          }}</span>
          <MoneyDisplay
            :value="(item.market_value_cents || 0) / 100"
            size="sm"
            :show-sign="false"
            :auto-color="false"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.institution-card {
  overflow: hidden;
  font-variant-numeric: tabular-nums;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  transition: box-shadow 0.2s ease;
}

.institution-card:hover {
  box-shadow: var(--shadow-overlay, var(--shadow-raised));
}

.card-head {
  display: flex;
  gap: var(--space-4, 16px);
  align-items: center;
  justify-content: space-between;
  padding: var(--space-standard, 18px);
  cursor: pointer;
}

.card-head:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.head-left {
  min-width: 0;
}

.institution-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.institution-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.head-right {
  display: flex;
  flex: none;
  gap: 10px;
  align-items: center;
}

.expand-icon {
  font-size: 14px;
  color: var(--text-tertiary);
  transition: transform 0.2s ease;
}

.expand-icon.is-expanded {
  transform: rotate(180deg);
}

.item-list {
  border-top: 1px solid var(--border-subtle, var(--border-light));
}

.item-row {
  display: flex;
  gap: var(--space-4, 16px);
  align-items: center;
  justify-content: space-between;
  padding: 10px var(--space-standard, 18px);
  border-bottom: 1px solid var(--border-subtle, var(--border-light));
}

.item-row:last-child {
  border-bottom: none;
}

.item-main {
  display: flex;
  gap: 8px;
  align-items: baseline;
  min-width: 0;
}

.item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  color: var(--text-primary);
  white-space: nowrap;
}

.item-code {
  flex: none;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-tertiary);
}

.item-metrics {
  display: flex;
  flex: none;
  gap: 16px;
  align-items: baseline;
}

.item-shares {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-secondary);
}

@media (width <= 520px) {
  .item-metrics {
    flex-direction: column;
    gap: 2px;
    align-items: flex-end;
  }
}

@media (prefers-reduced-motion: reduce) {
  .expand-icon {
    transition: none;
  }
}
</style>
