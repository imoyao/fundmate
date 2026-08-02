<!--
  MarketHeader · 探市 / 温度计 顶部导航（复用）
  品牌 logo + 页面 badge + 右侧导航按钮
  props:
    - logo:    品牌名（探市「多倍贝」/ 温度计「ShowBuy」）
    - badge:   页面标签文案（探市·研究 / 温度计）
    - navs:    导航项 [{ label, type?: 'link'|'primary', onClick }]
-->
<template>
  <header class="market-header">
    <div class="market-header__inner">
      <div class="market-header__logo-area">
        <span class="market-header__logo">{{ logo }}</span>
        <span class="market-header__badge">{{ badge }}</span>
      </div>
      <div class="market-header__nav">
        <template v-for="nav in navs" :key="nav.label">
          <el-button
            v-if="nav.type === 'primary'"
            class="market-header__btn"
            type="primary"
            size="small"
            @click="nav.onClick"
            >{{ nav.label }}</el-button
          >
          <el-button
            v-else-if="nav.type === 'primary-lg'"
            class="market-header__btn"
            type="primary"
            @click="nav.onClick"
            >{{ nav.label }}</el-button
          >
          <el-button
            v-else
            class="market-header__btn market-header__btn--link"
            link
            @click="nav.onClick"
            >{{ nav.label }}</el-button
          >
        </template>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    logo: string;
    badge: string;
    navs: Array<{
      label: string;
      type?: "link" | "primary" | "primary-lg";
      onClick?: () => void;
    }>;
  }>(),
  { logo: "多倍贝", badge: "" }
);
</script>

<style lang="scss" scoped>
.market-header {
  width: 100%;
  background: var(--bg-page);
  border-bottom: 1px solid var(--border-light);

  &__inner {
    max-width: 1400px;
    margin: 0 auto;
    padding: 16px var(--space-12);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
  }

  &__logo-area {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }

  &__logo {
    font-size: 20px;
    font-weight: 700;
    color: var(--text-primary);
  }

  &__badge {
    font-size: 12px;
    color: var(--text-tertiary);
    padding: 2px 10px;
    border: 1px solid var(--border-light);
    border-radius: var(--radius-pill);
    background: var(--bg-soft);
  }

  &__nav {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  &__btn--link {
    font-size: 14px;
    color: var(--text-secondary);
  }
}
</style>
