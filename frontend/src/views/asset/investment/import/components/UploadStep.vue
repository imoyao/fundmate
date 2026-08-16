<script setup lang="ts">
import ParsingStatus from "./ParsingStatus.vue";
import TemplateDownloadSection from "./TemplateDownloadSection.vue";
import SourceLogos from "./SourceLogos.vue";
import UploadArea from "./UploadArea.vue";
import FormatGuide from "./FormatGuide.vue";
import CreateLedgerDialog from "./CreateLedgerDialog.vue";
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

        <TemplateDownloadSection />

        <SourceLogos />

        <UploadArea />
      </div>

      <div v-if="formatGuides[selectedMode]" class="upload-right">
        <FormatGuide />
      </div>
    </div>

    <p
      style="
        margin-top: 24px;
        font-size: 13px;
        color: var(--text-tertiary);
        text-align: center;
      "
    >
      上传后将进入预览页面，您可以修正错误后确认导入。如有问题，请参考帮助文档。
    </p>

    <CreateLedgerDialog />
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
  align-items: flex-start;
  max-width: 1100px;
  margin: 0 auto;
}

.upload-left {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.upload-right {
  flex-shrink: 0;
  width: 340px;
  margin-top: 120px;
}

.ledger-select-area {
  margin-bottom: 16px;
}
</style>
