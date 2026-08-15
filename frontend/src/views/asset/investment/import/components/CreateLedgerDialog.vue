<script setup lang="ts">
import { ALLOCATION_OPTIONS } from "@/constants";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  showCreateLedgerDialog,
  createLedger,
  newLedgerName,
  newLedgerAllocation
} = useImportWizardContext();
</script>

<template>
  <el-dialog
    v-model="showCreateLedgerDialog"
    title="添加新账户"
    width="360px"
    :close-on-click-modal="false"
  >
    <el-form label-position="top">
      <el-form-item label="账户名称" required>
        <el-input
          v-model="newLedgerName"
          placeholder="例如：这是你的华泰证券或招商银行储蓄卡"
          size="large"
          @keyup.enter="createLedger"
        />
      </el-form-item>
      <el-form-item label="默认配置目标">
        <el-select v-model="newLedgerAllocation" size="large">
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
        <el-button type="primary" @click="createLedger">确认添加</el-button>
      </div>
    </template>
  </el-dialog>
</template>
