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

/** 下拉框底部"新建账户"选项的哨兵值（用负数避免与真实账户 id 冲突，且保持 number 类型） */
const CREATE_LEDGER_OPTION = -1;

function handleSelectChange(val: number) {
  if (val === CREATE_LEDGER_OPTION) {
    // 还原下拉值，避免把哨兵值写进 v-model，再打开新建弹窗
    resetNewLedgerForm();
    selectedLedgerId.value = null;
    showCreateLedgerDialog.value = true;
    return;
  }
  onAccountSelected(val);
}
</script>

<template>
  <div class="import-mode-group">
    <div class="account-select-area">
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

        <el-option :value="CREATE_LEDGER_OPTION" class="create-ledger-option">
          <span class="create-ledger-link">+ 新建账户</span>
        </el-option>
      </el-select>
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

.account-select {
  width: 100%;
}

/* 下拉分组标题：强分类，对齐设计语言（暖灰次要文字 + 500 字重） */
.account-select :deep(.el-select-group__title) {
  font-weight: 500;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

/* 下拉底部"新建账户"入口：浅灰分割线 + 蓝色链接 */
.account-select :deep(.create-ledger-option) {
  margin-top: 4px;
  border-top: 1px solid var(--border-default);
  color: var(--color-primary);
}

.account-select :deep(.create-ledger-link) {
  color: var(--color-primary);
  font-weight: 500;
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
