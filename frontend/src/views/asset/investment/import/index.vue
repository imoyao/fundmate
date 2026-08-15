<script setup lang="ts">
import FundMatchDrawer from "./components/FundMatchDrawer.vue";
import AiImportModal from "./components/AiImportModal.vue";
import LedgerSelectStep from "./components/LedgerSelectStep.vue";
import UploadStep from "./components/UploadStep.vue";
import PreviewStep from "./components/PreviewStep.vue";
import ResultStep from "./components/ResultStep.vue";
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
    <el-steps :active="currentStep" finish-status="success" align-center>
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
  </div>
</template>

<style scoped>
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
    background-color: var(--color-primary-10);
  }
  100% {
    background-color: transparent;
  }
}
.el-message--error {
  --el-message-text-color: var(--color-danger);
}
.text-error {
  color: var(--color-danger);
}
</style>
