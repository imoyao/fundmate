<script setup lang="ts">
/**
 * 表格空态（组合详情页三张表共用）。
 *
 * 单独成组件是为了**样式只有一份**：`.table-empty` 在「持仓明细 / 未归档持仓 /
 * 关联账户」三处都用，各自内联一份 scoped 样式会让同一条规则抄三遍（#980）。
 * 组件根节点即原来的 `<div class="table-empty">`，DOM 层级不变。
 */
defineOptions({ name: "PortfolioTableEmpty" });
</script>

<template>
  <div class="table-empty"><slot /></div>
</template>

<style scoped>
.table-empty {
  padding: var(--space-standard);
  color: var(--text-tertiary-ink);
  text-align: center;
}
</style>
