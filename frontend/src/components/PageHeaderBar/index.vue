<!--
  PageHeaderBar · 页面统一页头（组件级设计约束，详见 frontend/design.md）
  props:
    - title: 页面主标题
    - subtitle: 副标题（一句话说明这个页面是做什么的，面向小白用户）
    - updatedAt: 更新时间字符串（如 "2026-08-02 更新"），可选
-->
<template>
  <header class="page-header">
    <div class="page-header__text">
      <h1 class="page-header__title">{{ title }}</h1>
      <p v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="updatedAt" class="page-header__updated">
      <span class="page-header__dot" />
      <span>{{ updatedAt }}</span>
    </div>
  </header>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    subtitle?: string;
    updatedAt?: string;
  }>(),
  { title: "", subtitle: "", updatedAt: "" }
);
</script>

<style lang="scss" scoped>
/* 单一来源：frontend/design.md · 页头规范 */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: var(--space-section);

  &__title {
    font-size: 24px;
    font-weight: 700;
    color: var(--text-primary);
    margin: 0;
    line-height: 1.3;
  }

  &__subtitle {
    font-size: 14px;
    color: var(--text-secondary);
    margin: 6px 0 0;
    line-height: 1.5;
    max-width: 640px;
  }

  &__updated {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--text-tertiary);
    background: var(--bg-soft);
    border: 1px solid var(--border-light);
    padding: 4px 10px;
    border-radius: 999px;
    white-space: nowrap;
  }

  &__dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--c-success);
  }
}
</style>
