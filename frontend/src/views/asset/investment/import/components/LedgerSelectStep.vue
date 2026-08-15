<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  selectedLedgerId,
  onAccountSelected,
  ledgerGroups,
  ledgerTypeMap,
  goToManualEntry,
  openAiImport,
  goToLiabilityForm,
} = useImportWizardContext();
</script>

<template>
  <div class="import-mode-group">
    <h3 class="import-group-title">选择导入账户</h3>
    <div class="account-select-area">
      <el-select
        v-model="selectedLedgerId"
        placeholder="请选择要导入的账户"
        size="large"
        class="account-select"
        @change="onAccountSelected"
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
            <span class="ledger-option">
              <span>{{ ledger.name }}</span>
              <el-tag
                size="small"
                :type="ledger.ledger_type === 'family' ? 'info' : 'primary'"
              >
                {{ ledgerTypeMap[ledger.ledger_type] || ledger.ledger_type }}
              </el-tag>
            </span>
          </el-option>
        </el-option-group>
      </el-select>
      <p class="account-hint">
        选择账户后，系统将根据账户类型自动匹配导入模板。家庭账户不可用于导入交易数据。
      </p>
    </div>
  </div>

  <div class="import-mode-cards">
    <div class="mode-card" @click="goToManualEntry">
      <IconifyIconOffline icon="ep:edit" class="mode-icon" />
      <h4 class="mode-title">手动批量录入</h4>
      <p class="mode-desc">没有文件？在网页表格中逐行快速录入交易记录</p>
    </div>
    <div class="mode-card" @click="openAiImport">
      <IconifyIconOffline icon="ep:magic-stick" class="mode-icon" />
      <h4 class="mode-title">AI 截图/文本识别</h4>
      <p class="mode-desc">
        上传持仓/交易截图或粘贴文本，AI 识别后逐行核对入账
      </p>
    </div>
    <div class="mode-card" @click="goToLiabilityForm">
      <IconifyIconOffline icon="ep:document-add" class="mode-icon" />
      <h4 class="mode-title">录入负债 / 应收款</h4>
      <p class="mode-desc">记录信用卡、房贷等非交易类资产</p>
    </div>
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

.ledger-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.account-hint {
  margin-top: 12px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.import-mode-group {
  margin-bottom: 32px;
}

.import-group-title {
  padding-left: 4px;
  margin-bottom: 16px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
  border-left: 3px solid var(--color-primary);
}

.mode-card {
  width: 240px;
  padding: 32px 24px;
  text-align: center;
  cursor: pointer;
  background: var(--bg-card);
  border: 2px solid var(--border-default);
  border-radius: 16px;
  transition: all 0.3s ease;
}

.mode-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 8px 24px rgb(0 0 0 / 6%);
  transform: translateY(-2px);
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
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary);
}

.import-mode-cards {
  display: flex;
  gap: 20px;
  justify-content: center;
  margin-top: 32px;
}
</style>
