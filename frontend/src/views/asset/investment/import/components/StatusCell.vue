<script setup lang="ts">
import { computed } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const props = defineProps<{ row: any }>();

const { isRowBlocked, isFeeExplained, feeDiffOf } = useImportWizardContext();

/**
 * 警告态 tooltip：差额多少、为什么不算错。
 * 与「待补全」严格区分 —— 警告可导入，阻断不可导入。
 */
const feeHint = computed(() => {
  const diff = feeDiffOf(props.row);
  return (
    `金额比「数量×单价」多/少 ${diff.toFixed(2)} 元，等于该笔手续费。` +
    `入库时成交额按数量×单价记录、手续费单独一列，成本不受影响，可直接导入`
  );
});
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
  <el-tooltip
    v-else-if="isFeeExplained(row)"
    :content="feeHint"
    placement="top"
  >
    <el-tag type="warning" size="small">含手续费</el-tag>
  </el-tooltip>
  <el-tag v-else type="success" size="small">正常</el-tag>
</template>
