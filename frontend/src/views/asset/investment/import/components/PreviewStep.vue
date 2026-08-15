<script setup lang="ts">
import SummaryPanel from "./SummaryPanel.vue";
import PreviewTable from "./PreviewTable.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  currentStep,
  selectedLedgerName,
  toggleAllocationPanel,
  showAllocationGroupPanel,
  showLeftPanel,
  toggleLeftPanel,
  duplicateCount,
  blockedCount,
  errorCount,
  selectedCount,
  totalRows,
  importNormalOnly,
  importing,
  confirmImport
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

    <div class="step3-body">
      <SummaryPanel v-show="showLeftPanel" />
      <div
        class="step3-divider"
        :title="showLeftPanel ? '收起侧边栏' : '展开数据摘要'"
        @click="toggleLeftPanel"
      >
        <IconifyIconOffline
          :icon="showLeftPanel ? 'ep:d-arrow-left' : 'ep:d-arrow-right'"
          class="divider-icon"
        />
        <span v-if="!showLeftPanel" class="divider-text">摘要</span>
      </div>
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

.header-ledger {
  font-size: 15px;
  font-weight: 500;
  color: var(--text-primary);
}

.step3-body {
  display: flex;
  flex: 1;
  min-height: calc(100vh - 240px);
  overflow: hidden;
}

.step3-divider {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 16px;
  cursor: pointer;
  background: var(--bg-card);
  border-left: 1px solid var(--border-default);
  border-right: 1px solid var(--border-default);
  transition: background-color 0.2s;
}

.step3-divider:hover {
  background: var(--color-primary-10);
}

.step3-divider:hover .divider-icon {
  color: var(--color-primary);
}

.step3-divider:hover .divider-text {
  color: var(--color-primary);
}

.divider-icon {
  font-size: 16px;
  color: var(--text-tertiary);
  transition: color 0.2s;
}

.divider-text {
  writing-mode: vertical-lr;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
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
