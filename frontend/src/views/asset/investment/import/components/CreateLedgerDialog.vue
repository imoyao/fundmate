<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";
import AccountFormFields from "@/views/asset/ledgers/components/AccountFormFields.vue";
import { ALLOCATION_OPTIONS } from "@/constants";

const {
  showCreateLedgerDialog,
  createLedger,
  newLedgerName,
  newLedgerType,
  newLedgerLinkedCashId,
  newLedgerPortfolioId,
  newLedgerFeeConfig,
  newLedgerAllocation,
  cashLedgersForImport
} = useImportWizardContext();
</script>

<template>
  <el-dialog
    v-model="showCreateLedgerDialog"
    title="新建账户"
    width="480px"
    align-center
  >
    <el-form label-position="top">
      <el-form-item label="账户名称" required>
        <el-input
          v-model="newLedgerName"
          placeholder="如：华泰证券、天天基金"
          maxlength="30"
        />
      </el-form-item>

      <AccountFormFields
        v-model:ledger-type="newLedgerType"
        v-model:linked-cash-id="newLedgerLinkedCashId"
        v-model:portfolio-id="newLedgerPortfolioId"
        v-model:fee-config="newLedgerFeeConfig"
        :cash-ledgers="cashLedgersForImport"
        :portfolio-list="[]"
        :advanced-collapsed="true"
      />

      <el-form-item label="默认配置目标">
        <el-select v-model="newLedgerAllocation" class="w-full" clearable>
          <el-option
            v-for="opt in ALLOCATION_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="flex justify-end gap-3">
        <el-button @click="showCreateLedgerDialog = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!newLedgerName.trim()"
          @click="createLedger"
          >确认创建</el-button
        >
      </div>
    </template>
  </el-dialog>
</template>
