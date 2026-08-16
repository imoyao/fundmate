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
      >
        <span class="mode-option">
          <img
            v-if="mode.logo"
            :src="mode.logo"
            class="mode-option-logo"
            alt=""
          />
          <span>{{ mode.label }}</span>
        </span>
      </el-option>
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
  width: 240px;
}

.mode-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.mode-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.mode-option-logo {
  width: 18px;
  height: 18px;
  object-fit: contain;
}
</style>
