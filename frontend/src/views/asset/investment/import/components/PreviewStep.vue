<script setup lang="ts">
import SummaryPanel from "./SummaryPanel.vue";
import PreviewTable from "./PreviewTable.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  currentStep,
  selectedLedgerName,
  toggleAllocationPanel,
  showAllocationGroupPanel,
  duplicateCount,
  blockedCount,
  errorCount,
  selectedCount,
  totalRows,
  importNormalOnly,
  importing,
  confirmImport,
  showCashBindingBanner,
  cashLedgersForImport,
  bannerCashLedgerId,
  linkCashAccount,
  openCreateCashFromBanner
} = useImportWizardContext();
</script>

<template>
  <div class="step3-container">
    <div class="step3-header">
      <el-button size="default" @click="currentStep = 1">返回上一步</el-button>
      <span class="header-ledger">导入账户：{{ selectedLedgerName }}</span>
      <div class="header-actions ml-auto flex items-center gap-3">
        <el-button size="default" @click="toggleAllocationPanel">
          <IconifyIconOffline icon="ep:setting" class="mr-1" />
          {{ showAllocationGroupPanel ? "收起配置" : "设置配置目标" }}
        </el-button>
      </div>
    </div>

    <div v-if="showCashBindingBanner" class="cash-binding-banner">
      <IconifyIconOffline icon="ep:warning" class="banner-icon" />
      <span class="banner-text">
        检测到转账交易（银证转账）。当前账户「{{
          selectedLedgerName
        }}」未关联现金账户，建议关联以便记录资金流向：
      </span>
      <el-select
        v-model="bannerCashLedgerId"
        class="banner-select"
        size="small"
        clearable
        placeholder="选择现金账户"
        @change="linkCashAccount"
      >
        <el-option
          v-for="c in cashLedgersForImport"
          :key="c.id"
          :label="c.name"
          :value="c.id"
        />
      </el-select>
      <el-button
        class="banner-create-btn"
        size="small"
        link
        type="primary"
        @click="openCreateCashFromBanner"
        >+ 新建现金账户</el-button
      >
    </div>

    <div class="step3-body">
      <SummaryPanel />
      <PreviewTable />
    </div>

    <div class="fixed-action-bar">
      <div class="action-content">
        <span class="selected-count">
          本次导入识别 {{ totalRows }} 条，已选中
          <strong>{{ selectedCount }}</strong> 条有效数据
          <span v-if="duplicateCount + blockedCount + errorCount > 0">
            ，另有
            {{ duplicateCount + blockedCount + errorCount }} 条待处理（{{
              duplicateCount
            }}条重复 / {{ blockedCount }}条待补全
            <template v-if="errorCount > 0">/ {{ errorCount }}条错误</template
            >）
          </span>
        </span>
        <div class="flex gap-3">
          <el-button
            v-if="duplicateCount + blockedCount + errorCount > 0"
            :loading="importing"
            @click="importNormalOnly"
            >仅导入校验通过的数据
          </el-button>
          <el-button
            type="primary"
            :disabled="selectedCount === 0"
            :loading="importing"
            class="import-btn"
            @click="confirmImport"
            >确认导入 {{ selectedCount }} 条
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.step3-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.step3-header {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-default);
}

/* 步骤3 智能体检：未关联现金账户的银证转账提示横幅 */
.cash-binding-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 12px 16px 0;
  padding: 10px 14px;
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.banner-icon {
  color: var(--color-warning);
  font-size: 16px;
}

.banner-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.banner-select {
  width: 180px;
}

.banner-create-btn {
  font-weight: 500;
}

.header-ledger {
  font-size: 15px;
  font-weight: 500;
  color: var(--text-primary);
}

.step3-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: calc(100vh - 240px);
  overflow: hidden;
  padding: 16px;
  gap: 16px;
}

.fixed-action-bar {
  position: sticky;
  bottom: 0;
  z-index: 10;
  padding: 12px 16px;
  background: var(--bg-card);
  border-top: 1px solid var(--border-default);
}

.action-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1100px;
  margin: 0 auto;
}

.selected-count {
  font-size: 14px;
  color: var(--text-secondary);
}
</style>
