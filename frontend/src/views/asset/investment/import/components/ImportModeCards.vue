<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const router = useRouter();

const {
  selectedLedgerId,
  ledgerType,
  ledgerTypeLabel,
  availableModes,
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

// 持仓快照导入：跳过选账户步骤，后端自动归因决定账户归属
// 注意：路由经 formatTwoStageRoutes 拍平后注册为 /investment/eaccount-import，
// 用 name 跳转最稳妥（不依赖 path 层级，与 eaccount-import 内 goToReconcileCenter 同惯例）
function goToHoldingImport() {
  router.push({ name: "InvestmentEaccountImport" });
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

      <!-- 持仓快照导入：跳过选账户步骤，后端自动归因决定账户归属，故不受 accountSelected 锁定 -->
      <div class="mode-card" @click="goToHoldingImport">
        <IconifyIconOffline icon="ep:document" class="mode-icon" />
        <h4 class="mode-title">导入持仓快照</h4>
        <p class="mode-desc">上传平台导出的持仓文件，自动归入对应账户</p>
      </div>
    </div>

    <!-- 支持导入来源：复用 useImportWizard.availableModes 的平台 logo，体现专业性 -->
    <div class="vendor-support">
      <span class="vendor-label">支持导入来源</span>
      <div class="vendor-logos">
        <div
          v-for="m in availableModes"
          :key="m.value"
          class="vendor-item"
          :title="m.label"
        >
          <img v-if="m.logo" :src="m.logo" class="vendor-logo" alt="" />
          <span class="vendor-name">{{ m.label }}</span>
        </div>
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
  border-radius: var(--radius-lg);
  transition: all 0.3s ease;
}

.mode-card:not(.is-disabled):hover {
  border-color: var(--brand-700);
  box-shadow: var(--shadow-float);
  transform: translateY(-2px);
}

.mode-card.is-disabled {
  cursor: not-allowed;
  box-shadow: none;
  opacity: 0.5;
}

.mode-icon {
  margin-bottom: 12px;
  font-size: 36px;
  color: var(--brand-700);
}

.mode-title {
  margin: 0 0 8px;
  font-size: var(--text-body);
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
  color: var(--text-tertiary);
  text-align: center;
}

.vendor-support {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin-top: 28px;
}

.vendor-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

.vendor-logos {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  justify-content: center;
}

.vendor-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.vendor-logo {
  width: 22px;
  height: 22px;
  object-fit: contain;
}

.vendor-name {
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
