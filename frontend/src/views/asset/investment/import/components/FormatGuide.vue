<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const { formatGuides, selectedMode } = useImportWizardContext();
</script>

<template>
  <div v-if="formatGuides[selectedMode]" class="format-guide">
    <div class="format-guide-header">
      <IconifyIconOffline icon="ep:info-filled" class="format-guide-icon" />
      <span>{{ formatGuides[selectedMode].title }}</span>
    </div>
    <ol class="format-guide-list">
      <li v-for="(tip, index) in formatGuides[selectedMode].tips" :key="index">
        {{ tip }}
      </li>
    </ol>
  </div>
</template>

<style scoped>
.format-guide {
  padding: 16px;
  margin-top: 0;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: 0 1px 4px rgb(0 0 0 / 4%);
}

.format-guide-header {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.format-guide-icon {
  font-size: 18px;
  color: var(--color-primary);
}

.format-guide-list {
  padding-left: 0;
  margin: 0;
  list-style: none;
  counter-reset: step-counter;
}

.format-guide-list li {
  display: flex;
  align-items: baseline;
  margin-bottom: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  counter-increment: step-counter;
}

.format-guide-list li::before {
  flex-shrink: 0;
  min-width: 18px;
  margin-right: 8px;
  font-weight: 600;
  color: var(--color-primary);
  content: counter(step-counter) ".";
}
</style>
