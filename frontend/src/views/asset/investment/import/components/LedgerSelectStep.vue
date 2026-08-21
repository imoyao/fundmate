<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";
import ImportModeCards from "./ImportModeCards.vue";

const {
  selectedLedgerId,
  onAccountSelected,
  ledgerGroups,
  showCreateLedgerDialog,
  resetNewLedgerForm
} = useImportWizardContext();

function handleSelectChange(val: number) {
  onAccountSelected(val);
}

function handleCreateLedger() {
  resetNewLedgerForm();
  showCreateLedgerDialog.value = true;
}
</script>

<template>
  <div class="import-mode-group">
    <div class="account-select-area">
      <div class="account-select-row">
        <el-select
          v-model="selectedLedgerId"
          placeholder="请选择要导入的账户"
          size="large"
          class="account-select"
          @change="handleSelectChange"
        >
          <el-option-group
            v-for="group in ledgerGroups"
            :key="group.label"
            :label="group.label"
          >
            <el-option
              v-for="ledger in group.ledgers"
              :key="ledger.id"
              :label="ledger.name"
              :value="ledger.id"
              :disabled="ledger.ledger_type === 'family'"
            >
              {{ ledger.name }}
            </el-option>
          </el-option-group>
        </el-select>
        <el-button
          class="account-create-btn"
          size="large"
          @click="handleCreateLedger"
        >
          <IconifyIconOffline icon="ep:plus" />
          <span>新建账户</span>
        </el-button>
      </div>
      <p class="account-hint">
        选择账户后，系统将根据账户类型自动匹配导入模板。家庭账户不可用于导入交易数据。
      </p>
    </div>

    <ImportModeCards />
  </div>
</template>

<style scoped>
.account-select-area {
  max-width: 520px;
  padding: 24px 0;
  margin: 0 auto;
  text-align: center;
}

.account-select-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.account-select {
  flex: 1;
}

/* 下拉分组标题：强分类，对齐设计语言（暖灰次要文字 + 500 字重） */
.account-select :deep(.el-select-group__title) {
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--text-secondary);
}

/* 新建账户：次按钮语义（辅助操作，不抢主视觉），对齐 design.md 按钮规范 */
.account-create-btn {
  flex-shrink: 0;
  gap: 4px;
  height: 40px;
  padding: 0 16px;
  color: var(--text-primary);
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  transition:
    background-color 150ms ease,
    border-color 150ms ease;
}

.account-create-btn:hover {
  background-color: var(--bg-hover);
  border-color: var(--border-light);
}

.account-create-btn :deep(.el-icon) {
  margin-right: 0;
}

.account-hint {
  margin-top: 12px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.import-mode-group {
  margin-bottom: 24px;
}
</style>
