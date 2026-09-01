<!-- src/components/ProductDisplay/index.vue -->
<template>
  <div :class="['product-cell', { 'product-cell--compact': compact }]">
    <!-- 紧凑模式（数据密集表格专用）：名称 + 代码同行，行高压到 20px。
         对齐 design.md「数据表格强制紧凑原则」：自选/资产总览/交易流水等
         密集场景行高锁定 40–44px，名称列不得再拆成多行。 -->
    <template v-if="compact">
      <span class="product-name">{{ name || symbol || "--" }}</span>
      <span class="product-code-compact" :title="symbol || ''">
        {{ symbol || "--" }}
      </span>
      <span v-if="typeLabel" class="product-type-compact">
        {{ typeLabel }}
      </span>
    </template>

    <!-- 默认两行模式：非数据密集页面（持仓/账本/清单明细等）沿用 -->
    <template v-else>
      <div class="product-name">
        {{ name || symbol || "--" }}
      </div>
      <div class="product-code-row">
        <span class="product-code"># {{ symbol || "--" }}</span>
        <span v-if="typeLabel" class="type-tag-inline">
          {{ typeLabel }}
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
defineProps({
  /** 持仓名称，如 "金地集团" */
  name: { type: String, default: "" },
  /** 资产代码，如 "SH600383" */
  symbol: { type: String, default: "" },
  /** 资产类型中文标签，如 "股票"、"基金" */
  typeLabel: { type: String, default: "" },
  /**
   * 紧凑模式：名称与代码同行单行展示，用于数据密集表格（自选）。
   * 默认 false，保持其余复用方（探市/持仓明细/账本明细/清单）原两行布局不受影响。
   */
  compact: { type: Boolean, default: false }
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

/* ── 紧凑模式（数据密集表格）：名称 + 代码 + 类型 同行单行 ──
   行内容高度 20px，配合 el-table 行高 40px 基线，保证一屏行数最大化
   （design.md「数据表格强制紧凑原则」：自选等密集场景行高锁定 40–44px）。
   名称靠 min-width:0 + ellipsis 截断，避免长名称把代码挤出列宽。 */
.product-cell--compact {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
  line-height: 20px;
}

.product-cell--compact .product-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.product-code-compact {
  flex-shrink: 0;
  font-family: var(--font-number);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

/* 类型以弱化小字呈现（非色块）：既不占行高，也避免「仅靠颜色传意」 */
.product-type-compact {
  flex-shrink: 0;
  padding: 0 4px;
  font-size: 11px;
  line-height: 16px;
  color: var(--text-tertiary);
  background-color: var(--bg-soft);
  border-radius: var(--radius-sm);
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
