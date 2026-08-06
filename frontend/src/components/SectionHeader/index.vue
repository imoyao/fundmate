<!--
  SectionHeader · 区块统一标题行（设计系统强制复用，详见 frontend/design.md）
  - 标题 + 可选信息图标（hover/焦点显示 tooltip）+ 右侧操作槽（具名插槽 #action）
  - 禁止各页面再手写 <h2>/<h3> + 分散的图标/操作按钮，统一收口到本组件
  props:
    - title:   区块标题
    - info:    信息图标 tooltip 文案（可选；不传则不显示图标）
    - icon:    信息图标名（可选，默认 ep:info-filled）
-->
<template>
  <div class="section-header">
    <div class="section-header__title-group">
      <h2 class="section-header__title">{{ title }}</h2>
      <el-tooltip v-if="info" :content="info" placement="top">
        <span
          class="section-header__info"
          tabindex="0"
          role="img"
          :aria-label="info"
        >
          <IconifyIconOffline :icon="icon" />
        </span>
      </el-tooltip>
    </div>
    <div v-if="$slots.action" class="section-header__action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";

withDefaults(
  defineProps<{
    title?: string;
    info?: string;
    icon?: string;
  }>(),
  {
    title: "",
    info: "",
    icon: "ep:info-filled"
  }
);
</script>

<style lang="scss" scoped>
/* 单一来源：frontend/design.md · 区块标题统一规范 */
.section-header {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  min-height: 32px; /* 与历史实现 h-8 对齐，保证右侧操作槽垂直居中 */
  margin-bottom: var(--space-3);

  &__title-group {
    display: flex;
    gap: 6px;
    align-items: center;
    min-width: 0;
  }

  &__title {
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 16px;
    font-weight: 600;
    line-height: 1.4;
    color: var(--text-primary);
    white-space: nowrap;
  }

  &__info {
    display: inline-flex;
    flex-shrink: 0;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    color: var(--text-tertiary);
    cursor: help;
    transition: color 0.15s ease;

    &:hover,
    &:focus-visible {
      color: var(--brand-700);
      outline: none;
    }
  }

  &__action {
    display: inline-flex;
    flex-shrink: 0;
    gap: 8px;
    align-items: center;
  }
}
</style>
