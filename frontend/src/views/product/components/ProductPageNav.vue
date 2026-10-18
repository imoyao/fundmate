<!--
  ProductPageNav · 详情页页内导航·顶部锚点胶囊（#1968 子卡）

  形态登记：调研结论 docs/working-notes/product-detail-research-2026-10-12.md §5.3 ——
  `< xl` 内容区顶部胶囊（横向可滑、sticky 在页头下）；`xl+` 让位给右侧目录 rail
  （ProductPageToc）。**刻意不挂 tablist 语义角色**：guard_segmented 只登记两类
  例外（分组胶囊 Tab / 二级筛选栏），页内导航是「跳转」不是「切换视图」，
  不往白名单里塞第三条。视觉语言对齐已登记的 `.road-pill--soft`
  （软胶囊 + --brand-100 选中底），不另造一套。

  视觉规范见 docs/design/components.md「相邻多选一语言」表。
-->
<script setup lang="ts">
import type { PageNavItem } from "../composables/useProductPageNav";

defineProps<{
  items: PageNavItem[];
  activeId: string;
}>();

const emit = defineEmits<{
  (e: "navigate", id: string): void;
}>();
</script>

<template>
  <nav class="page-nav" aria-label="本页导航">
    <button
      v-for="item in items"
      :key="item.id"
      type="button"
      class="page-nav__pill"
      :class="{ 'is-active': item.id === activeId }"
      :aria-current="item.id === activeId ? 'location' : undefined"
      @click="emit('navigate', item.id)"
    >
      {{ item.label }}
    </button>
  </nav>
</template>

<style scoped lang="scss">
@use "@/style/breakpoints" as bp;

.page-nav {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  gap: 6px;
  align-items: center;
  padding: var(--space-2) 0;

  /* 与首张卡片的间距走 margin 而不是 padding：padding 会加高吸顶条的遮挡高度 */
  margin-bottom: var(--space-3);
  overflow-x: auto;
  scrollbar-width: thin;
  background: var(--bg-page);

  /* xl+ 由右目录 rail 接管，胶囊整条让位（不重复承担同一职能） */
  @include bp.above("xl") {
    display: none;
  }
}

.page-nav__pill {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  background: var(--bg-soft);
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  transition:
    background-color 0.15s ease,
    color 0.15s ease,
    border-color 0.15s ease;

  &:hover {
    background: var(--bg-hover);
  }

  &.is-active {
    color: var(--brand-ink); /* #2314：前景文字用品牌文字级 */
    background: var(--brand-100);
    border-color: var(--brand-400);
  }
}
</style>
