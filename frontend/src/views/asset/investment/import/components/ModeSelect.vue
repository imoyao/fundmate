<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const { selectedMode, availableModes } = useImportWizardContext();
</script>

<template>
  <div class="mode-select">
    <span class="mode-label">导入格式：</span>
    <el-select v-model="selectedMode" size="large" class="mode-select-field">
      <el-option
        v-for="mode in availableModes"
        :key="mode.value"
        :label="mode.label"
        :value="mode.value"
      />
    </el-select>
    <span class="mode-hint">选择与您的文件来源匹配的格式</span>
  </div>
</template>

<style scoped>
.mode-select {
  display: flex;
  gap: 8px;
  align-items: center;
}

.mode-label {
  font-size: 14px;
  color: var(--text-secondary);
}

.mode-select-field {
  width: 220px;
}

.mode-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
