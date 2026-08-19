<script setup lang="ts">
import { ALLOCATION_OPTIONS } from "@/constants";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const props = defineProps<{ row: any }>();
const { onRowAllocationChange } = useImportWizardContext();

function handleChange(val: string) {
  // row 是父组件持有的共享可变数据对象（previewRows 元素），按引用原地修改是预期行为
  // eslint-disable-next-line vue/no-mutating-props
  props.row.allocation = val;
  onRowAllocationChange(props.row);
}
</script>

<template>
  <el-select
    :model-value="row.allocation"
    size="small"
    :disabled="row.is_cash_transfer || row.is_duplicate || row.error"
    @change="handleChange"
  >
    <el-option
      v-for="opt in ALLOCATION_OPTIONS"
      :key="opt.value"
      :label="opt.label"
      :value="opt.value"
    />
  </el-select>
</template>
