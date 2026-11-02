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
      <!-- 备注列已并入本行（2026-11-02 换列给手续费让位）：空间不足时由备注先让出，
           代码与类型标签保持完整，hover 看全文 -->
      <span v-if="row.notes" class="product-notes" :title="row.notes">{{
        row.notes
      }}</span>
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
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.product-code-row {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

.product-code {
  flex: 0 0 auto;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 备注：唯一可压缩项，超出截断（title 给全文） */
.product-notes {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.type-tag-inline {
  flex: 0 0 auto;
  height: 20px;
  padding: 0 6px;
  font-size: var(--text-label);
  line-height: 20px;
  color: var(--text-inverse);
  border: none;
}
</style>
