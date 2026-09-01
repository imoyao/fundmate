<script setup lang="ts">
import FundMatchDrawer from "./components/FundMatchDrawer.vue";
import AiImportModal from "./components/AiImportModal.vue";
import LedgerSelectStep from "./components/LedgerSelectStep.vue";
import UploadStep from "./components/UploadStep.vue";
import PreviewStep from "./components/PreviewStep.vue";
import ResultStep from "./components/ResultStep.vue";
import CreateLedgerDialog from "./components/CreateLedgerDialog.vue";
import { ref } from "vue";
import { useImportWizard } from "./composables/useImportWizard";
import { provideWizard } from "./composables/useImportWizardContext";
import { Edit } from "@element-plus/icons-vue";

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
  onAiRowsFound,
  devMode,
  devJump,
  draftBannerVisible,
  pendingDraftMeta,
  restoreDraft,
  discardCurrentDraft
} = wizard;

// 调试快进面板：仅开发环境可见；勾选后跳到预览/结果时注入模拟数据
const withMock = ref(false);
</script>

<template>
  <div class="inventory-page">
    <header class="import-header">
      <h1 class="import-title">导入交易</h1>
      <p class="import-subtitle">
        从券商或表格文件批量导入交易记录，支持自动识别与人工核对。
      </p>
    </header>

    <!-- #1239 草稿层：同域（C）草稿恢复 Banner，不弹窗打断 -->
    <div
      v-if="draftBannerVisible && pendingDraftMeta"
      class="draft-banner"
      role="alert"
    >
      <el-icon class="draft-banner-icon"><Edit /></el-icon>
      <div class="draft-banner-text">
        发现{{ pendingDraftMeta.savedAt ? "未完成" : "" }}的导入草稿（{{
          pendingDraftMeta.rowCount
        }}
        条记录），是否继续？
      </div>
      <div class="draft-banner-actions">
        <el-button size="small" type="primary" @click="restoreDraft">
          恢复草稿
        </el-button>
        <el-button size="small" text @click="discardCurrentDraft">
          丢弃
        </el-button>
      </div>
    </div>

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
        :class="{ 'dev-step-clickable': devMode }"
        @click="devMode && devJump(index, withMock)"
      />
    </el-steps>

    <div class="step-content">
      <LedgerSelectStep v-if="currentStep === 0" />
      <UploadStep v-else-if="currentStep === 1" />
      <PreviewStep v-else-if="currentStep === 2" />
      <ResultStep v-else />
    </div>

    <!-- 调试快进面板：仅开发环境可见，跳过前序步骤直达目标步骤 -->
    <div v-if="devMode" class="dev-jump-panel">
      <div class="dev-jump-title">调试快进（DEV）</div>
      <div class="dev-jump-row">
        <el-button size="small" @click="devJump(0)">步骤1 选账户</el-button>
        <el-button size="small" @click="devJump(1)">步骤2 上传</el-button>
        <el-button size="small" @click="devJump(2, withMock)"
          >步骤3 预览</el-button
        >
        <el-button size="small" @click="devJump(3, withMock)"
          >步骤4 结果</el-button
        >
      </div>
      <label class="dev-jump-check">
        <input v-model="withMock" type="checkbox" />
        跳到预览/结果时注入模拟数据
      </label>
      <div class="dev-jump-hint">模拟数据仅用于查看布局，确认导入会写库</div>
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

/* #1239 草稿恢复 Banner：中性信息色，非红非弹窗（柔性原则 §2.5） */
.draft-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 16px;
  padding: 12px 16px;
  font-size: var(--text-small);
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.draft-banner-icon {
  font-size: 16px;
  color: var(--brand-700);
}

.draft-banner-text {
  flex: 1;
}

.draft-banner-actions {
  display: flex;
  gap: 8px;
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

.dev-step-clickable :deep(.el-step__head),
.dev-step-clickable :deep(.el-step__title) {
  cursor: pointer;
}

.dev-jump-panel {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 1000;
  max-width: 280px;
  padding: 12px 14px;
  font-size: var(--text-small);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  box-shadow: 0 4px 16px rgb(0 0 0 / 12%);
}

.dev-jump-title {
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--text-primary);
}

.dev-jump-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.dev-jump-check {
  display: flex;
  gap: 4px;
  align-items: center;
  margin-top: 8px;
  color: var(--text-secondary);
}

.dev-jump-hint {
  margin-top: 6px;
  color: var(--text-tertiary);
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
