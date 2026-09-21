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
@use "@/style/breakpoints" as bp;

/* 单一来源：frontend/design.md · 页头规范 */
.page-header {
  display: flex;
  gap: var(--space-compact);
  align-items: flex-start;
  justify-content: space-between;
  max-width: var(--layout-content-width);
  padding: 0 var(--space-standard);
  margin: 0 auto var(--space-section);

  /* 窄屏（< 768px）：文字块与更新时间胶囊改为上下排。
     横排时胶囊固定 181px 宽、文字块只能分到剩余空间（375 视口实测仅 129.8px，
     副标题被迫折 4 行）；改列向后副标题拿满整行宽度，同时保住信息优先级
     标题 > 副标题 > 时间戳，也无需给副标题加截断 / tooltip（那会丢信息）。
     横向内边距同步从 --space-standard(24px) 收到 --space-compact(16px)。

     ⚠️ 本块必须留在**基础声明之后**：@include 编译成 @media，而媒体查询不改变
     特异性——挪到 `display: flex` 等声明之前，下面的 gap / padding 覆盖会被
     基础声明压掉（`stylelint --fix` 曾自动这么挪，见 stylelint.config.js 的
     order/order 注解）。 */
  @include bp.below("md") {
    flex-direction: column;
    gap: var(--space-2);
    align-items: flex-start;
    padding: 0 var(--space-compact);

    /* 列向下文字块自身撑满整行（align-items:flex-start 会让它退化成 fit-content，
       短副标题的页面就会出现「盒子只有一行字宽」的抖动） */
    .page-header__text {
      align-self: stretch;
    }
  }

  /* 文字块必须显式允许收缩（flex 项默认 min-width:auto，即不低于 min-content）：
     否则标题块的下限 + 右侧 nowrap 的更新时间胶囊会一起撑破容器，
     把副标题挤成 4 行并让文档横向溢出。
     只加 min-width，不改 flex 简写——桌面档文字块维持 fit-content，
     像素与改动前逐字相同。 */
  &__text {
    min-width: 0;
  }

  &__title {
    margin: 0;

    /* D17：页面主标题统一走 --text-display（32px/300 细体），design.md 字阶系统 */
    font-size: var(--text-display);
    font-weight: 300;
    line-height: 1.3;
    color: var(--text-primary);
    letter-spacing: -0.3px;
  }

  &__subtitle {
    max-width: 640px;
    margin: 6px 0 0;
    font-size: 14px;
    line-height: 1.5;
    color: var(--text-secondary);
  }

  &__updated {
    display: inline-flex;
    flex: 0 0 auto;
    gap: 6px;
    align-items: center;
    padding: 4px 10px;
    font-size: 12px;
    color: var(--text-tertiary-ink);
    white-space: nowrap;
    background: var(--bg-soft);
    border: 1px solid var(--border-light);
    border-radius: 999px;
  }

  &__dot {
    width: 6px;
    height: 6px;
    background: var(--color-success);
    border-radius: 50%;
  }
}
</style>
