<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const { fileSize } = useImportWizardContext();
</script>

<template>
  <div class="parsing-status">
    <p class="text-sm text-gray-500 mb-4">
      <IconifyIconOffline icon="ep:loading" class="loading-icon" />
      正在解析文件，请稍候...
    </p>
    <p class="text-xs text-gray-400 mb-4">
      正在处理 {{ fileSize }}，预计需要 5-10 秒
    </p>
    <el-skeleton :rows="8" animated />
  </div>
</template>

<style scoped>
.parsing-status {
  width: 100%;
  max-width: 680px;
  margin: 0 auto;
  text-align: center;
}

.loading-icon {
  margin-right: 4px;
  font-size: 16px;
  animation: spin 1s linear infinite;
}
</style>
