<script setup lang="ts">
// 分组标题行：色点 + 分类名 + 计数。
// 折叠态摘要与展开态分组头本来就渲染同一组三个 span，只是计数文案不同
// （「N 个标的」vs 裸数字），故收成多根片段组件——不额外包元素，DOM 与拆分前逐字一致。
import { categoryColor } from "./assetOverviewModel";

defineProps<{
  category: string;
  /** 计数文案；null 表示尚未取数，整段不渲染（不编造数字） */
  countText: string | null;
}>();
</script>

<template>
  <span
    class="asset-group__dot"
    :style="{ background: categoryColor(category) }"
  />
  <span class="asset-group__title">{{ category }}</span>
  <span v-if="countText !== null" class="asset-group__count">{{
    countText
  }}</span>
</template>

<style lang="scss" scoped>
.asset-group__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.asset-group__title {
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.asset-group__count {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
