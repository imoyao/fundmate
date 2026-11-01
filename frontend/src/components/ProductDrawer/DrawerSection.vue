<!--
  DrawerSection · 抽屉内的区块标题行（docs/design/product-detail-drawer.md §5）

  刻意**不复用** `SectionHeader`：那是卡级语义（16/600），进抽屉会与 20/600 的
  产品名层级倒挂。这里用同一份「13/500 --text-secondary、上 32 下 12、不画线」的
  抽屉语言，右侧放 13/400 辅助（如「共 12 条」）。

  样式在 `_pd.scss`（`.pd-sec*`），与外壳同一份来源；本组件由外壳引入，
  单独使用不会有样式，也不该单独使用。
-->
<template>
  <section class="pd-sec">
    <div class="pd-sec__head">
      <h3 class="pd-sec__title">{{ title }}</h3>
      <div v-if="$slots.action" class="pd-sec__action">
        <slot name="action" />
      </div>
    </div>
    <slot />
  </section>
</template>

<script setup lang="ts">
defineOptions({ name: "DrawerSection" });

defineProps<{
  /** 区块标题（「持有」「投顾信息」「交易记录」…） */
  title: string;
}>();
</script>
