<!--
  CardBlock · 区块卡片容器（强制复用，见 docs/design/components.md）
  - 统一「--bg-card + --radius-lg + --border-light + --shadow-raised + --space-standard」
  - 供「区块标题（SectionHeader）+ 内容区」这类区块卡使用，禁止各页面手写
    bg-white rounded-2xl p-6 shadow-sm border 等重复样式
-->
<template>
  <section class="card-block">
    <slot />
  </section>
</template>

<script setup lang="ts">
// 纯容器组件，无 props / 逻辑
</script>

<style lang="scss" scoped>
.card-block {
  padding: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}
</style>
