<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";
import SummaryStats from "./SummaryStats.vue";
import BatchFixPanel from "./BatchFixPanel.vue";
import AllocationGroupPanel from "./AllocationGroupPanel.vue";

const { showLeftPanel } = useImportWizardContext();
</script>

<template>
  <div class="step3-left" :class="{ collapsed: !showLeftPanel }">
    <SummaryStats />
    <BatchFixPanel />
    <AllocationGroupPanel />
  </div>
</template>

<style scoped>
.step3-left {
  flex-shrink: 0;
  width: 320px;
  padding: 16px;
  overflow-y: auto;
  background: var(--bg-card);
  border-right: 1px solid var(--border-default);
}

.step3-left.collapsed {
  display: none;
}
</style>
