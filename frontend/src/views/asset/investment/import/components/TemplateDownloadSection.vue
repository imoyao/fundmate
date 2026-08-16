<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  isStandardMode,
  downloadLoading,
  handleDownloadTemplate,
  templateNameForAccount,
  accountType,
  templateFields
} = useImportWizardContext();
</script>

<template>
  <div v-if="isStandardMode" class="template-download-section">
    <el-button
      size="large"
      class="download-template-btn"
      :loading="downloadLoading"
      @click="handleDownloadTemplate"
    >
      <IconifyIconOffline icon="ep:download" class="mr-2" />
      下载{{ templateNameForAccount }}（CSV）
    </el-button>
    <p class="download-hint">
      按模板填写后上传，即可批量导入{{ accountType }}交易记录<br />
      模板包含：{{ templateFields }}
    </p>
  </div>
</template>

<style scoped>
.template-download-section {
  margin: 0 0 16px;
  text-align: left;
}

.download-template-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  padding: 0 20px;
  font-size: 14px;
  color: var(--brand-700);
  background: var(--brand-100);
  border: 1px solid var(--brand-400);
  border-radius: var(--radius-sm);
  transition:
    background-color 150ms ease,
    border-color 150ms ease;
}

.download-template-btn:hover:not(:disabled) {
  color: var(--brand-700);
  background: var(--brand-200);
  border-color: var(--brand-600);
}

.download-hint {
  max-width: 700px;
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  text-align: left;
}
</style>
