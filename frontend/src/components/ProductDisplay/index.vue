<!-- src/components/ProductDisplay/index.vue -->
<template>
  <div :class="['product-cell', { 'product-cell--compact': compact }]">
    <!-- 紧凑模式（数据密集表格专用）：两行「名称 / 代码 + 类型 + 附加信息」。
         注意「紧凑」= 两行紧凑，不是「单行压扁」：#1281 曾把名称、代码、类型、
         标签全塞进同一行（单行 20px），实测长名称被挤到只显示两三个字、完全不可读。
         现改为两行：名称独占一行（完整展示、溢出省略 + title 全名），
         代码 / 类型 / 标签 chips 走第二行弱化小字，行内容高度 42px
         （名称 20 + gap 2 + 元信息 20）。
         附加信息（如自选的标签 chips / 添加标签按钮）经 #meta 插槽注入第二行，
         避免在其它页面复制一套产品列结构。 -->
    <template v-if="compact">
      <span class="product-name" :title="name || symbol || ''">
        {{ name || symbol || "--" }}
      </span>
      <div class="product-meta-row">
        <span class="product-code-compact" :title="symbol || ''">
          # {{ symbol || "--" }}
        </span>
        <span v-if="typeLabel" class="product-type-compact">
          {{ typeLabel }}
        </span>
        <slot name="meta" />
      </div>
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
   * 紧凑模式：名称一行 + 「# 代码 / 类型 / #meta 插槽」一行的两行紧凑结构，
   * 用于数据密集表格（自选）。默认 false，保持其余复用方（探市/持仓明细/账本明细/清单）
   * 原两行布局不受影响。
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

/* ── 紧凑模式（数据密集表格）：名称一行 + 元信息（代码/类型/插槽）一行 ──
   行内容 42px = 名称 20 + gap 2 + 元信息 20；配合单元格 6px 上下 padding 落在 54px
   （自选页行高基线，见 design.md「Table · 行高例外」），是旧三行式（约 78px）的七成。
   多出来的高度换回「名称完整可读 + 标签文字可见」，是 #1281 两轮实测后确认的取舍。
   名称靠 min-width:0 + ellipsis 截断，溢出由 title 兜全名（表格列不再用
   show-overflow-tooltip：EP 会给单元格加 white-space:nowrap，会把两行结构压回一行）。 */
.product-cell--compact {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  cursor: default;
}

.product-cell--compact .product-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  color: var(--text-primary);
  white-space: nowrap;
}

/* 元信息行：代码 + 类型 + 外部注入内容（标签 chips / 添加标签按钮）统一 20px 高，不撑高行 */
.product-meta-row {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
  height: 20px;
}

.product-code-compact {
  flex-shrink: 0;
  font-family: var(--font-number);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  line-height: 20px;
  color: var(--text-tertiary);
}

/* 类型以弱化小字呈现（非色块）：既不占行高，也避免「仅靠颜色传意」 */
.product-type-compact {
  flex-shrink: 0;
  padding: 0 4px;
  font-size: 11px;
  line-height: 20px;
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
