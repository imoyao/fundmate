<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

defineProps<{ row: any }>();

const { getFundTypeColor } = useImportWizardContext();
</script>

<template>
  <div class="product-cell">
    <span class="product-name">{{ row.name || row.symbol || "--" }}</span>
    <div class="product-code-row">
      <span class="product-code"># {{ row.symbol || "--" }}</span>
      <el-tag
        v-if="row.display_type"
        size="small"
        :color="getFundTypeColor(row.display_type)"
        class="type-tag-inline"
        >{{ row.display_type }}
      </el-tag>
    </div>
  </div>
</template>

<style scoped>
.product-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.3;
}

.product-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.product-code-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.product-code {
  font-size: 12px;
  color: var(--text-tertiary);
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
