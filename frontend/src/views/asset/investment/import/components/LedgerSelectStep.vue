<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";
import ImportModeCards from "./ImportModeCards.vue";

const { selectedLedgerId, onAccountSelected, ledgerGroups, ledgerTypeMap } =
  useImportWizardContext();
</script>

<template>
  <div class="import-mode-group">
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
  margin-bottom: 24px;
}
</style>
