<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";
import { ASSET_TYPE_LABELS } from "@/constants/assetType";

defineProps<{ row: any }>();

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
  gap: 6px;
  align-items: center;
}

.op-type-label {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
}

.type-tag-inline {
  height: 20px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 20px;
  color: var(--bg-card);
  border: none;
}
</style>
