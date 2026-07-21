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

.product-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.product-code-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.product-code {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 类型标签样式优化 */
.type-tag-inline {
  font-size: 11px;
  padding: 0 8px;
  height: 20px;
  line-height: 20px;
  border-radius: 8px;
  border: 1px solid var(--border-default); /* 加个极细的边框，更有质感 */
  color: var(--text-secondary);
  background-color: var(--bg-page);
}
</style>
