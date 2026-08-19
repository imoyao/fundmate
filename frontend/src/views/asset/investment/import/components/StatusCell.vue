<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

defineProps<{ row: any }>();

const { isRowBlocked } = useImportWizardContext();
</script>

<template>
  <el-tooltip
    v-if="row.is_duplicate"
    content="该交易已存在于系统中，默认跳过。如需强制导入，请手动勾选"
    placement="top"
  >
    <el-tag type="warning" size="small">重复</el-tag>
  </el-tooltip>
  <el-tag v-else-if="row.error" type="danger" size="small">错误</el-tag>
  <el-tag v-else-if="isRowBlocked(row)" type="info" size="small">待补全</el-tag>
  <el-tag v-else type="success" size="small">正常</el-tag>
</template>
