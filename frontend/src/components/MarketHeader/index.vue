<!--
  MarketHeader · 探市 / 温度计 顶部导航（复用）
  品牌 logo + 页面 badge + 右侧导航按钮
  props:
    - logo:    品牌名（统一「多多贝」，见 config.ts 的 MARKET_LOGO）
    - badge:   页面标签文案（探市 / 温度计）
    - navs:    导航项 [{ label, type?: 'link'|'primary', onClick }]
-->
<template>
  <header class="market-header">
    <div class="market-header__inner">
      <div
        class="market-header__logo-area"
        role="button"
        tabindex="0"
        @click="emit('logo-click')"
        @keyup.enter="emit('logo-click')"
      >
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

const emit = defineEmits<{
  "logo-click": [];
}>();

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
  { logo: "多多贝", badge: "" }
);
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.market-header {
  width: 100%;
  background: var(--bg-page);
  border-bottom: 1px solid var(--border-light);

  &__inner {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-standard);
    align-items: center;
    justify-content: space-between;
    max-width: var(--layout-shell-width);
    padding: 16px var(--space-12);
    margin: 0 auto;

    /* 侧边距按档位收窄。48px 的横向内边距在 375 视口要吃掉 96px（占 26%），
       是顶栏 logo / badge 被迫断行的直接原因；收窄后内容区拿到 100% 余量。

       ⚠️ 这两块必须留在基础声明**之后**：@include 编译成 @media，而媒体查询不改变
       特异性——挪到 `padding: 16px var(--space-12)` 之前，下面的覆盖就会被它压掉
       （`stylelint --fix` 曾自动这么挪，见 stylelint.config.js 的 order/order 注解）。 */
    @include bp.below("lg") {
      padding: 16px var(--space-standard);
    }

    @include bp.below("md") {
      gap: var(--space-2) var(--space-3);
      padding: 12px var(--space-compact);
    }
  }

  &__logo-area {
    display: flex;
    gap: 10px;
    align-items: center;

    /* 品牌名与页面 badge 不允许断行：375 视口下「多多贝」曾被折成「多多/贝」、
       badge「探市」被折成「探/市」——中文可在任意字间断行，故必须显式禁用。 */
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
  }

  &__logo {
    font-size: 20px;
    font-weight: 700;
    color: var(--text-primary);

    @include bp.below("sm") {
      font-size: 18px;
    }
  }

  &__badge {
    padding: 2px 10px;
    font-size: 12px;
    color: var(--text-tertiary-ink);
    white-space: nowrap;
    background: var(--bg-soft);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-pill);
  }

  &__nav {
    display: flex;

    /* 导航不参与收缩：按钮文字被压会先断行（el-button 默认 nowrap，
       实际表现是整行被顶出容器），空间不足时交给 __inner 的 flex-wrap 换行承接。 */
    flex-shrink: 0;
    gap: 12px;
    align-items: center;
  }

  &__btn--link {
    font-size: 14px;
    color: var(--text-secondary);
  }
}
</style>
