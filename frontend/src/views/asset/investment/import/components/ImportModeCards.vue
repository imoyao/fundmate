<script setup lang="ts">
import { computed } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  selectedLedgerId,
  ledgerType,
  ledgerTypeLabel,
  goToManualEntry,
  openAiImport,
  goToLiabilityForm
} = useImportWizardContext();

// I-1：未选择账户时三张卡片整体禁用灰显，选中后亮起可点
const accountSelected = computed(() => !!selectedLedgerId.value);

// I-2：卡片文案按账户类型动态变化
const manualPreset = computed(() => {
  switch (ledgerType.value) {
    case "stock":
      return {
        title: "录入股票交割单",
        desc: "在网页表格中逐行录入股票交易记录"
      };
    case "fund":
    case "cash":
      return {
        title: "录入基金对账单",
        desc: "在网页表格中逐行录入基金交易记录"
      };
    case "bond":
      return {
        title: "录入可转债记录",
        desc: "在网页表格中逐行录入可转债交易"
      };
    default:
      return {
        title: "手动批量录入",
        desc: "没有文件？在网页表格中逐行快速录入交易记录"
      };
  }
});

const aiPreset = computed(() => {
  if (!accountSelected.value) {
    return "上传持仓/交易截图或粘贴文本，AI 识别后逐行核对入账";
  }
  return `上传${ledgerTypeLabel.value}截图或粘贴文本，AI 识别后逐行核对入账`;
});

function onManualEntry() {
  if (!accountSelected.value) return;
  goToManualEntry();
}

function onAiImport() {
  if (!accountSelected.value) return;
  openAiImport();
}

function onLiability() {
  if (!accountSelected.value) return;
  goToLiabilityForm();
}
</script>

<template>
  <div class="import-mode-wrapper">
    <div class="import-mode-cards" :class="{ 'is-locked': !accountSelected }">
      <div
        class="mode-card"
        :class="{ 'is-disabled': !accountSelected }"
        @click="onManualEntry"
      >
        <IconifyIconOffline icon="ep:edit" class="mode-icon" />
        <h4 class="mode-title">{{ manualPreset.title }}</h4>
        <p class="mode-desc">{{ manualPreset.desc }}</p>
      </div>

      <div
        class="mode-card"
        :class="{ 'is-disabled': !accountSelected }"
        @click="onAiImport"
      >
        <IconifyIconOffline icon="ep:magic-stick" class="mode-icon" />
        <h4 class="mode-title">AI 截图/文本识别</h4>
        <p class="mode-desc">{{ aiPreset }}</p>
      </div>

      <div
        class="mode-card"
        :class="{ 'is-disabled': !accountSelected }"
        @click="onLiability"
      >
        <IconifyIconOffline icon="ep:document-add" class="mode-icon" />
        <h4 class="mode-title">录入负债 / 应收款</h4>
        <p class="mode-desc">记录信用卡、房贷等非交易类资产</p>
      </div>
    </div>

    <p v-if="!accountSelected" class="mode-cards-lock-hint">
      请先在上方选择导入账户，再选择录入方式
    </p>
  </div>
</template>

<style scoped>
.import-mode-wrapper {
  margin-top: 8px;
}

.import-mode-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  justify-content: center;
  margin-top: 32px;
}

.mode-card {
  width: 240px;
  max-width: 100%;
  padding: 32px 24px;
  text-align: center;
  cursor: pointer;
  background: var(--bg-card);
  border: 2px solid var(--border-default);
  border-radius: 16px;
  transition: all 0.3s ease;
}

.mode-card:not(.is-disabled):hover {
  border-color: var(--color-primary);
  box-shadow: 0 8px 24px rgb(0 0 0 / 6%);
  transform: translateY(-2px);
}

.mode-card.is-disabled {
  cursor: not-allowed;
  opacity: 0.5;
  box-shadow: none;
}

.mode-icon {
  margin-bottom: 12px;
  font-size: 36px;
  color: var(--color-primary);
}

.mode-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.mode-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary);
}

.mode-cards-lock-hint {
  margin-top: 16px;
  font-size: 13px;
  text-align: center;
  color: var(--text-tertiary);
}
</style>
