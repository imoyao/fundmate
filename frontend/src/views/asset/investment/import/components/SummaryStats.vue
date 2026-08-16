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
  flex-direction: row;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.summary-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 14px;
  border: 1px solid var(--border-default);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition:
    background-color 0.2s,
    color 0.2s,
    border-color 0.2s;
}

.summary-tab:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.summary-tab.active {
  background: var(--color-primary-10);
  border-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: 600;
}

.tab-icon {
  font-size: 14px;
}

.tab-count {
  min-width: 18px;
  text-align: center;
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--bg-secondary);
  color: var(--text-tertiary);
}

.summary-tab.active .tab-count {
  background: var(--color-primary);
  color: #fff;
}
</style>
