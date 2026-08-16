<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const { isStandardMode, accountType, templateFields } = useImportWizardContext();
</script>

<template>
  <div v-if="isStandardMode" class="template-download-section">
    <p class="download-hint">
      按模板填写后上传，即可批量导入{{ accountType }}交易记录<br />
      模板包含：{{ templateFields }}
    </p>
  </div>
</template>

<style scoped>
.template-download-section {
  margin: 0;
  text-align: left;
}

.download-hint {
  max-width: 700px;
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-tertiary);
  text-align: left;
}
</style>
