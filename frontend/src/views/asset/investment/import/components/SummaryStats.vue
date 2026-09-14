<script setup lang="ts">
import { computed } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  totalRows,
  errorCount,
  duplicateCount,
  blockedCount,
  tableStatusFilter
} = useImportWizardContext();

/** 顶部胶囊 Tab：全部 / 已校验 / 重复项 / 待确认，点击联动表格过滤 */
const tabs = computed(() => [
  {
    key: "all",
    label: "全部",
    count: totalRows.value,
    icon: "ep:document"
  },
  {
    key: "normal",
    label: "已校验",
    count:
      totalRows.value -
      errorCount.value -
      duplicateCount.value -
      blockedCount.value,
    icon: "ep:select"
  },
  {
    key: "duplicate",
    label: "重复项",
    count: duplicateCount.value,
    icon: "ep:copy-document"
  },
  {
    key: "problem",
    label: "待确认",
    count: errorCount.value + duplicateCount.value + blockedCount.value,
    icon: "ep:warning"
  }
]);

function setFilter(key: string) {
  tableStatusFilter.value = key === "all" ? "all" : key;
}
</script>

<template>
  <div class="summary-tabs">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      class="summary-tab"
      :class="{ active: tableStatusFilter === tab.key }"
      type="button"
      @click="setFilter(tab.key)"
    >
      <IconifyIconOffline :icon="tab.icon" class="tab-icon" />
      <span>{{ tab.label }}</span>
      <span class="tab-count">{{ tab.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.summary-tabs {
  display: flex;
  flex-flow: row wrap;
  gap: 8px;
  align-items: center;
}

.summary-tab {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 30px;
  padding: 0 14px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 999px;
  transition:
    background-color 0.2s,
    color 0.2s,
    border-color 0.2s;
}

.summary-tab:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
}

.summary-tab.active {
  font-weight: 600;
  color: var(--color-primary);
  background: var(--color-primary-10);
  border-color: var(--color-primary);
}

.tab-icon {
  font-size: 14px;
}

.tab-count {
  min-width: 18px;
  padding: 0 6px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
  text-align: center;
  background: var(--bg-secondary);
  border-radius: 999px;
}

.summary-tab.active .tab-count {
  color: var(--text-inverse);
  background: var(--color-primary);
}
</style>
