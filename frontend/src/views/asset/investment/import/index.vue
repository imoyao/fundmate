<script setup lang="ts">
import FundMatchDrawer from "./components/FundMatchDrawer.vue";
import AiImportModal from "./components/AiImportModal.vue";
import LedgerSelectStep from "./components/LedgerSelectStep.vue";
import UploadStep from "./components/UploadStep.vue";
import PreviewStep from "./components/PreviewStep.vue";
import ResultStep from "./components/ResultStep.vue";
import CreateLedgerDialog from "./components/CreateLedgerDialog.vue";
import { useImportWizard } from "./composables/useImportWizard";
import { provideWizard } from "./composables/useImportWizardContext";

const wizard = useImportWizard();
provideWizard(wizard);

const {
  currentStep,
  steps,
  showMatchDrawer,
  missingFundNames,
  previewData,
  onMatchComplete,
  showAiModal,
  selectedLedgerId,
  onAiRowsFound
} = wizard;
</script>

<template>
  <div class="inventory-page">
    <header class="import-header">
      <h1 class="import-title">导入交易</h1>
      <p class="import-subtitle">
        从券商或表格文件批量导入交易记录，支持自动识别与人工核对。
      </p>
    </header>

    <el-steps
      :active="currentStep"
      finish-status="success"
      align-center
      class="import-steps"
    >
      <el-step
        v-for="(step, index) in steps"
        :key="index"
        :title="step.title"
      />
    </el-steps>

    <div class="step-content">
      <LedgerSelectStep v-if="currentStep === 0" />
      <UploadStep v-else-if="currentStep === 1" />
      <PreviewStep v-else-if="currentStep === 2" />
      <ResultStep v-else />
    </div>

    <FundMatchDrawer
      :visible="showMatchDrawer"
      :missing-fund-names="missingFundNames"
      :preview-data="previewData"
      @match-complete="onMatchComplete"
    />
    <AiImportModal
      v-model="showAiModal"
      :ledger-id="selectedLedgerId"
      @rows-found="onAiRowsFound"
    />

    <CreateLedgerDialog />
  </div>
</template>

<style scoped>
.import-header {
  margin-bottom: 24px;
}

.import-title {
  margin: 0 0 8px;
  font-size: var(--text-display);
  font-weight: 300;
  color: var(--text-primary);
}

.import-subtitle {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-tertiary);
}

.import-steps {
  margin-bottom: 32px;
}

:deep(.el-step__head.is-finish) {
  cursor: pointer;
}
:deep(.el-step__title.is-finish) {
  cursor: pointer;
}
</style>

<style>
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
@keyframes ledger-flash {
  0% {
    background-color: var(--brand-100);
  }
  100% {
    background-color: transparent;
  }
}
.el-message--error {
  --el-message-text-color: var(--color-danger-system);
}
.text-error {
  color: var(--color-danger-system);
}
</style>
