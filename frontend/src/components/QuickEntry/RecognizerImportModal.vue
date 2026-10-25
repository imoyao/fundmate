<template>
  <el-dialog
    v-model="visible"
    class="recognizer-import-dialog"
    title="AI 识别入库"
    width="720px"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <RecognizerUsageBanner
      :remaining="remaining"
      :quota="quota"
      :occupied="occupied"
    />

    <!-- 场景切换：交易识别 / 持仓识别（决定落入域 C / 域 A）；scenarioLock 时隐藏。
         收敛到 SegmentedControl（design.md「Segmented」唯一实现，见 docs/design/components.md）；
         识别在途时整组禁用（disabled），与原先逐按钮 :disabled 等价 -->
    <SegmentedControl
      v-if="!scenarioLock"
      :model-value="scenario"
      :options="SCENARIO_OPTIONS"
      :disabled="recognizing"
      block
      aria-label="识别场景"
      class="recognizer-tabs"
      @change="switchScenario"
    />

    <!-- 交易识别需选择关联账户（域 C 对账按账本隔离） -->
    <div v-if="scenario === 'txn_import'" class="ledger-select">
      <span class="ledger-select__label">关联账户</span>
      <el-select
        v-model="selectedLedgerId"
        placeholder="选择交易账户（可选）"
        clearable
        class="ledger-select__input"
      >
        <el-option
          v-for="ledger in ledgers"
          :key="ledger.id"
          :label="ledger.name"
          :value="ledger.id"
        />
      </el-select>
    </div>

    <!-- 输入方式：上传图片 / 粘贴文本 -->
    <SegmentedControl
      :model-value="activeTab"
      :options="IMPORT_TAB_OPTIONS"
      block
      aria-label="输入方式"
      class="recognizer-tabs recognizer-tabs--sub"
      @change="switchTab"
    />

    <RecognizerInputPanel
      ref="inputPanelRef"
      v-model:image-file="imageFile"
      v-model:text-content="textContent"
      v-model:text-error="textError"
      :scenario="scenario"
      :active-tab="activeTab"
    />

    <RecognizerPreviewTable
      v-if="previewRows.length > 0"
      :rows="previewRows"
      :scenario="scenario"
    />

    <template #footer>
      <el-button class="ocr-cancel-btn" size="large" @click="visible = false"
        >取消</el-button
      >
      <el-button
        v-if="previewRows.length === 0"
        type="primary"
        size="large"
        :loading="recognizing"
        :disabled="!canRecognize"
        class="ocr-primary-btn"
        @click="handleRecognize"
      >
        {{ recognizing ? "识别中…" : "开始识别" }}
      </el-button>
      <template v-else>
        <el-button size="large" @click="resetPreview">重新识别</el-button>
        <el-button
          type="primary"
          size="large"
          :loading="saving"
          class="ocr-primary-btn"
          @click="handleSaveDraft"
        >
          确认进草稿（{{ previewRows.length }}）
        </el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import type { OcrScenario } from "@/api/ocr";
import {
  IMPORT_TAB_OPTIONS,
  SCENARIO_OPTIONS
} from "./recognizerImport/recognizerImportModel";
import { useRecognizerImport } from "./recognizerImport/useRecognizerImport";
import RecognizerUsageBanner from "./recognizerImport/RecognizerUsageBanner.vue";
import RecognizerInputPanel from "./recognizerImport/RecognizerInputPanel.vue";
import RecognizerPreviewTable from "./recognizerImport/RecognizerPreviewTable.vue";

const props = defineProps<{
  modelValue: boolean;
  /** 锁定识别场景（隐藏场景切换 tab）。托盘/快捷入口只接单一场景时用，如 'txn_import' */
  scenarioLock?: OcrScenario;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  saved: [domain: "A" | "C"];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

const inputPanelRef = ref<InstanceType<typeof RecognizerInputPanel>>();

const {
  scenario,
  activeTab,
  imageFile,
  textContent,
  textError,
  recognizing,
  saving,
  previewRows,
  remaining,
  quota,
  occupied,
  ledgers,
  selectedLedgerId,
  canRecognize,
  switchScenario,
  switchTab,
  handleRecognize,
  handleSaveDraft,
  resetPreview
} = useRecognizerImport({
  visible: () => props.modelValue,
  scenarioLock: () => props.scenarioLock,
  onSaved: domain => emit("saved", domain),
  onClose: () => {
    visible.value = false;
  },
  focusTextarea: () => inputPanelRef.value?.focus()
});
</script>

<style scoped lang="scss">
/* 弹窗外壳的 :deep 必须留在本文件：`.recognizer-import-dialog` 落在 el-overlay 上，
   `.el-dialog` 是它的后代，编译出的 `[data-v-x] .el-dialog` 才匹配得上。
   若随组件搬走（el-dialog 变成根元素自身）选择器会静默失配、退回 EP 默认观感。 */
.recognizer-import-dialog {
  :deep(.el-dialog) {
    overflow: hidden;
    background-color: var(--bg-card);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-modal);
  }

  :deep(.el-dialog__body) {
    padding: var(--space-standard);
    margin: 0;
  }
}

.recognizer-tabs {
  margin-bottom: var(--space-standard);

  /* 输入方式组：与上方场景组之间留出间隔（外观全部由 SegmentedControl 负责） */
  &--sub {
    margin-top: var(--space-standard);
  }
}

.ledger-select {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-standard);

  &__label {
    font-size: var(--text-small);
    color: var(--text-secondary);
    white-space: nowrap;
  }

  &__input {
    flex: 1;
  }
}

.ocr-primary-btn,
.ocr-cancel-btn {
  height: 40px;
  padding: 0 24px;
  font-size: var(--text-small);
  border: none;
  border-radius: 6px;
  transition:
    transform 120ms ease,
    background-color 150ms ease;
}

.ocr-primary-btn:active:not(:disabled),
.ocr-cancel-btn:active:not(:disabled) {
  transform: translateY(1px);
}

.ocr-primary-btn {
  color: var(--text-inverse);
  background-color: var(--brand-solid);
}

.ocr-primary-btn:hover:not(:disabled) {
  background-color: var(--brand-solid-hover);
}

.ocr-primary-btn:disabled {
  /* audit-text-contrast: exempt .ocr-primary-btn:disabled 为**真禁用**控件，按 WCAG 1.4.3 对 inactive component 的豁免；**「无数据占位符」不适用本豁免**（那是信息，须用 --text-tertiary-ink）。登记见 docs/spec/tech-debt.md（#1599） */
  color: var(--text-disabled);
  cursor: not allowed;
  background-color: var(--bg-muted);
  box-shadow: none;
  transform: none;
}

.ocr-cancel-btn {
  color: var(--text-primary);
  background-color: var(--bg-soft);
}

.ocr-cancel-btn:hover:not(:disabled) {
  background-color: var(--bg-hover);
}
</style>
