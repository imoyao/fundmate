<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";
import SummaryStats from "./SummaryStats.vue";
import BatchFixPanel from "./BatchFixPanel.vue";
import AllocationGroupPanel from "./AllocationGroupPanel.vue";

useImportWizardContext();
</script>

<template>
  <div class="step3-topbar">
    <SummaryStats />
    <BatchFixPanel />
    <AllocationGroupPanel />
  </div>
</template>

<style scoped>
.step3-topbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: stretch;
}

.step3-topbar > :deep(*) {
  flex: 1 1 240px;
  min-width: 240px;
}
</style>
