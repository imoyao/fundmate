<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  selectedMode,
  availableModes,
  isStandardMode,
  downloadLoading,
  handleDownloadTemplate,
  templateNameForAccount
} = useImportWizardContext();
</script>

<template>
  <div class="mode-select">
    <div class="mode-main">
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
      <button
        v-if="isStandardMode"
        type="button"
        class="download-template-btn"
        :disabled="downloadLoading"
        @click="handleDownloadTemplate"
      >
        <IconifyIconOffline icon="lucide:download" class="download-icon" />
        <span>{{ downloadLoading ? "下载中..." : `下载${templateNameForAccount}模板` }}</span>
      </button>
    </div>
    <span class="mode-hint">选择与您的文件来源匹配的格式</span>
  </div>
</template>

<style scoped>
.mode-select {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.mode-main {
  display: flex;
  gap: 12px;
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

.download-template-btn {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 0;
  font-size: 13px;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color 150ms ease;
}

.download-template-btn:hover:not(:disabled) {
  color: var(--text-primary);
}

.download-template-btn:disabled {
  cursor: default;
  opacity: 0.6;
}

.download-icon {
  font-size: 16px;
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
