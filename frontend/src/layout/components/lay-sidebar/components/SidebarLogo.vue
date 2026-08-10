<script setup lang="ts">
import { getTopMenu } from "@/router/utils";
import { useNav } from "@/layout/hooks/useNav";
import BrandLogo from "@/components/BrandLogo/index.vue";

defineProps({
  collapse: Boolean
});

const { title } = useNav();
</script>

<template>
  <div class="sidebar-logo-container" :class="{ collapses: collapse }">
    <transition name="sidebarLogoFade">
      <router-link
        v-if="collapse"
        key="collapse"
        :title="title"
        class="sidebar-logo-link"
        :to="getTopMenu()?.path ?? '/'"
      >
        <BrandLogo :size="32" />
        <span class="sidebar-title dbb-brand">
          {{ title }}
          <span class="brand-sub">投资账本</span>
        </span>
      </router-link>
      <router-link
        v-else
        key="expand"
        :title="title"
        class="sidebar-logo-link"
        :to="getTopMenu()?.path ?? '/'"
      >
        <BrandLogo :size="32" />
        <span class="sidebar-title dbb-brand">
          {{ title }}
          <span class="brand-sub">投资账本</span>
          <span class="brand-beta">Beta</span>
        </span>
      </router-link>
    </transition>
  </div>
</template>

<style lang="scss" scoped>
.sidebar-logo-container {
  position: relative;
  width: 100%;
  height: 48px;
  overflow: hidden;

  .sidebar-logo-link {
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
    height: 100%;
    padding-left: 10px;

    &:hover {
      text-decoration: none;
    }
  }

  .sidebar-title {
    display: inline-flex;
    align-items: baseline;
    height: 32px;
    margin: 2px 0 0 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 18px;
    font-weight: 600;
    line-height: 32px;
    color: var(--pure-theme-sub-menu-active-text);
    white-space: nowrap;
  }

  /* 品牌文字组：副标 0.6em(φ⁻¹ 黄金分割比) + · 分隔 + Beta 挂件上浮（与品牌 v1.7 横排组合一致） */
  .dbb-brand {
    .brand-sub {
      margin-left: 0.25em;
      font-size: 0.6em;
      font-weight: 400;
      color: var(--pure-theme-sub-menu-active-text);
      opacity: 0.72;

      &::before {
        margin-right: 0.25em;
        color: inherit;
        content: "·";
      }
    }

    .brand-beta {
      position: relative;
      top: -0.35em;
      display: inline-flex;
      align-items: center;
      padding: 1px 6px;
      margin-left: 6px;
      font-size: 0.55rem;
      font-weight: 600;
      line-height: 1;
      color: var(--el-color-primary);
      white-space: nowrap;
      background: rgb(242 163 142 / 14%);
      border: 1px solid var(--el-color-primary-light-5);
      border-radius: 6px;
    }
  }
}
</style>
