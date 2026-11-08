<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";
import type { PreviewRow } from "../composables/previewRow";
import { ASSET_TYPE_LABELS } from "@/constants/assetType";

defineProps<{ row: PreviewRow }>();

const { getTypeColor } = useImportWizardContext();
</script>

<template>
  <div class="op-type-cell">
    <span class="op-type-label">{{ row.op_type_label || "--" }}</span>
    <el-tag
      v-if="!row.is_merged && row.type !== 'fund'"
      :color="getTypeColor(row.type)"
      size="small"
      class="type-tag-inline"
      >{{ ASSET_TYPE_LABELS[row.type] || row.type || "未知" }}
    </el-tag>
  </div>
</template>

<style scoped>
.op-type-cell {
  display: flex;

  /* #2836：允许折行。104px 下「现金分红 + 可转债」这类组合放不下，标签会被
     单元格裁成「可转」——资产类型直接丢失。加宽列会把总宽顶出预算
     （1060px，见 feeColumnLayout.spec.ts），而产品列本来就是「名称 / 代码」
     两行结构，这里跟着折到第二行反而与它对齐，行高也不变（仍由产品列决定）。
     gap 拆开行列：行间距 2px，列间距 6px。 */
  flex-wrap: wrap;
  gap: 2px 6px;
  align-items: center;
}

.op-type-label {
  font-size: var(--text-label);
  color: var(--text-primary);
  white-space: nowrap;
}

.type-tag-inline {
  height: 20px;
  padding: 0 6px;
  font-size: var(--text-label);
  line-height: 20px;
  color: var(--text-inverse);
  border: none;
}
</style>
