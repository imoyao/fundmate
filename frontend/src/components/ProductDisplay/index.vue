<!-- src/components/ProductDisplay/index.vue -->
<template>
  <div class="product-cell">
    <div class="product-name">
      {{ name || symbol || "--" }}
    </div>
    <div class="product-code-row">
      <span class="product-code"># {{ symbol || "--" }}</span>
      <span v-if="typeLabel" class="type-tag-inline">
        {{ typeLabel }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps({
  /** 持仓名称，如 "金地集团" */
  name: { type: String, default: "" },
  /** 资产代码，如 "SH600383" */
  symbol: { type: String, default: "" },
  /** 资产类型中文标签，如 "股票"、"基金" */
  typeLabel: { type: String, default: "" }
});
</script>

<style scoped>
.product-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.3;
  cursor: pointer; /* 增加鼠标手型提示，暗示可点击 */
}

/* 名称单行截断：配合 el-table-column 的 show-overflow-tooltip，
   名称超宽时显示省略号、hover 出完整名称（tooltip 只对单行文本生效） */
.product-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
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

/* 类型标签样式优化 */
.type-tag-inline {
  height: 20px;
  padding: 0 8px;
  font-size: 11px;
  line-height: 20px;
  color: var(--text-secondary);
  background-color: var(--bg-page);
  border: 1px solid var(--border-default); /* 加个极细的边框，更有质感 */
  border-radius: 8px;
}
</style>
