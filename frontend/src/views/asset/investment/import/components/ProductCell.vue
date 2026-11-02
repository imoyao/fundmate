<script setup lang="ts">
import { computed } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const props = defineProps<{ row: any }>();

const { getFundTypeColor } = useImportWizardContext();

/**
 * 类型标签是否在本列显示。
 *
 * 「操作类型」列（OpTypeCell）已经显示过资产类型标签（买入 · 股票），本列再显示一次
 * 是把同一条信息说两遍——代价还是从最紧的备注里扣的：实测 1440 视口下备被压成「备…」。
 * 故只在「这一列才有」的情况下显示：
 * - 基金：OpTypeCell 对 fund 不显示类型标签，而基金的类型（股票型/债券型…）只在这里；
 * - 合并行：OpTypeCell 对 is_merged 行也不显示。
 */
const showTypeTag = computed(() => {
  const r = props.row;
  if (!r.display_type) return false;
  return r.type === "fund" || Boolean(r.is_merged);
});
</script>

<template>
  <div class="product-cell">
    <span class="product-name">{{ row.name || row.symbol || "--" }}</span>
    <div class="product-code-row">
      <span class="product-code"># {{ row.symbol || "--" }}</span>
      <el-tag
        v-if="showTypeTag"
        size="small"
        :color="getFundTypeColor(row.display_type)"
        class="type-tag-inline"
        >{{ row.display_type }}
      </el-tag>
      <!-- 备注列已并入本行（2026-11-02 换列给手续费让位）：空间不足时由备注先让出，
           代码保持完整，hover 看全文 -->
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
