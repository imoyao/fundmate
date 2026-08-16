<script setup lang="ts">
import ParsingStatus from "./ParsingStatus.vue";
import TemplateDownloadSection from "./TemplateDownloadSection.vue";
import ModeSelect from "./ModeSelect.vue";
import UploadArea from "./UploadArea.vue";
import FormatGuide from "./FormatGuide.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  selectedLedgerName,
  ledgerTypeLabel,
  currentStep,
  formatGuides,
  selectedMode,
  parsing
} = useImportWizardContext();
</script>

<template>
  <div class="upload-step">
    <ParsingStatus v-show="parsing" />

    <div v-show="!parsing" class="upload-layout">
      <div class="upload-left">
        <div class="ledger-select-area">
          <div class="flex items-center gap-4">
            <span class="text-base font-medium text-[var(--text-primary)]"
              >交易账户：</span
            >
            <el-tag size="large" type="primary"
              >{{ selectedLedgerName }}（{{ ledgerTypeLabel }}）</el-tag
            >
            <el-button type="primary" link @click="currentStep = 0"
              >更换账户</el-button
            >
          </div>
        </div>

        <ModeSelect />

        <TemplateDownloadSection />

        <UploadArea />
      </div>

      <div v-if="formatGuides[selectedMode]" class="upload-right">
        <FormatGuide />
      </div>
    </div>
  </div>
</template>

<style scoped>
.upload-step {
  min-height: 380px;
  padding: 0;
}

.upload-layout {
  display: flex;
  gap: 24px;
  align-items: stretch;
  max-width: 1100px;
  margin: 0 auto;
}

.upload-left {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  gap: 20px;
}

.upload-right {
  display: flex;
  flex: 1 1 340px;
  max-width: 360px;
  min-width: 300px;
}

.upload-right :deep(.format-guide) {
  flex: 1;
  width: 100%;
  min-height: 360px;
  padding: 20px 24px;
  margin-top: 0;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  box-shadow: var(--shadow-raised);
}

.ledger-select-area {
  margin-bottom: 0;
}
</style>
