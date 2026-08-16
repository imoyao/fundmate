<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

defineProps<{ row: any }>();

const { isRowSelected, isRowBlocked, handleRowCheckboxChange } =
  useImportWizardContext();
</script>

<template>
  <el-tooltip
    v-if="row.is_cash_transfer"
    content="资金划转暂不支持导入"
    placement="top"
  >
    <el-checkbox :model-value="false" disabled />
  </el-tooltip>
  <el-checkbox
    v-else
    :model-value="isRowSelected(row)"
    :disabled="row.is_duplicate || row.error || isRowBlocked(row)"
    @change="(val: boolean) => handleRowCheckboxChange(row, val)"
  />

  <el-tag v-if="row.is_calculated" size="small" type="warning" class="ml-1"
    >待确认</el-tag
  >
</template>
