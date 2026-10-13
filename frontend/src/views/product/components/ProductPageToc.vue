<!--
  ProductPageToc · 详情页页内导航·右侧目录 rail（#1968 子卡）

  形态登记：调研结论 docs/working-notes/product-detail-research-2026-10-12.md §5.3 ——
  `xl+`（>=1280）右侧 sticky 目录，宽 160px，锚点列表（无视觉标题，理由见 template 注释）。
  为什么不做左栏：全局 NavVertical 已在左（240px），双左栏视觉打架且随折叠
  宽度抖动（调研 §5.2，Agent 页 session-history 是反面先例）。右侧补空不抢宽。

  与顶部胶囊（ProductPageNav）共用同一份 items / activeId（父级经 composable 下发），
  两级互斥呈现：<xl 胶囊、xl+ rail，`display` 由断点切换。
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
  <!-- 无视觉标题：产品页的 rail 语义是「快捷跳转」不是「内容大纲」，
       条目自己会说话（我的持仓/走势/交易记录），再加一个「本页目录」
       小标题只会多占 20px 垂直空间 + 一次视觉停顿。文档站 TOC 带标题
       是文档语境的惯例，不适用于产品详情页。可访问名称由 aria-label
       提供（读屏用户需要知道这个 aside 是什么；若同时保留视觉标题，
       屏幕阅读器会读到两次「本页目录」）。 -->
  <aside class="page-toc" aria-label="本页目录">
    <ul class="page-toc__list">
      <li v-for="item in items" :key="item.id">
        <button
          type="button"
          class="page-toc__link"
          :class="{ 'is-active': item.id === activeId }"
          :aria-current="item.id === activeId ? 'location' : undefined"
          @click="emit('navigate', item.id)"
        >
          {{ item.label }}
        </button>
      </li>
    </ul>
  </aside>
</template>

<style scoped lang="scss">
@use "@/style/breakpoints" as bp;

.page-toc {
  /* <xl 不占位：胶囊栏是窄屏形态（移动端天然横向可滑） */
  display: none;

  @include bp.above("xl") {
    position: sticky;

    /* 贴在滚动容器顶部下方一点；fixedHeader 下容器顶沿即全局页头下沿。
       16px 用 --space-compact（与 Agent 页 session-history 同款偏移）——
       没有 --space-4 这个令牌（check_css_vars 会当幽灵令牌拦下）。 */
    top: var(--space-compact);
    display: block;
    flex-shrink: 0;
    align-self: flex-start;
    width: 160px;
    border-left: 1px solid var(--border-light);
  }
}

.page-toc__list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.page-toc__link {
  display: block;
  width: 100%;
  padding: 5px var(--space-3);
  margin-left: -1px; /* 让选中指示条压在 1px 轨道上，不留双线 */
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
  background: none;
  border: none;
  border-left: 2px solid transparent;
  transition: color 0.15s ease;

  &:hover {
    color: var(--text-primary);
  }

  &.is-active {
    font-weight: 600;
    color: var(--brand-700);
    border-left-color: var(--brand-700);
  }
}
</style>
