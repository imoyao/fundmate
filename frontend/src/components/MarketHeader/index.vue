<!--
  MarketHeader · 探市 / 温度计 顶部导航（复用）
  品牌 logo + 页面 badge + 右侧导航按钮
  props:
    - logo:    品牌名（统一「多倍贝」，见 config.ts 的 MARKET_LOGO）
    - badge:   页面标签文案（探市 / 温度计）
    - navs:    导航项 [{ label, type?: 'link'|'primary', onClick }]
-->
<template>
  <header class="market-header">
    <div class="market-header__inner">
      <div class="market-header__logo-area">
        <BrandLogo :size="24" />
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
import BrandLogo from "@/components/BrandLogo/index.vue";

withDefaults(
  defineProps<{
    logo?: string;
    badge?: string;
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
    display: flex;
    gap: 24px;
    align-items: center;
    justify-content: space-between;
    max-width: 1400px;
    padding: 16px var(--space-12);
    margin: 0 auto;
  }

  &__logo-area {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  &__logo {
    font-size: 20px;
    font-weight: 700;
    color: var(--text-primary);
  }

  &__badge {
    padding: 2px 10px;
    font-size: 12px;
    color: var(--text-tertiary);
    background: var(--bg-soft);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-pill);
  }

  &__nav {
    display: flex;
    gap: 12px;
    align-items: center;
  }

  &__btn--link {
    font-size: 14px;
    color: var(--text-secondary);
  }
}
</style>
