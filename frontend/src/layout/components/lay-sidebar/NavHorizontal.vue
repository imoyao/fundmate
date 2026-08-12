<script setup lang="ts">
import { emitter } from "@/utils/mitt";
import { useNav } from "@/layout/hooks/useNav";
import LaySearch from "../lay-search/index.vue";
import LayNotice from "../lay-notice/index.vue";
import { responsiveStorageNameSpace } from "@/config";
import { ref, nextTick, computed, onMounted } from "vue";
import { storageLocal, isAllEmpty } from "@pureadmin/utils";
import { usePermissionStoreHook } from "@/store/modules/permission";
import LaySidebarItem from "../lay-sidebar/components/SidebarItem.vue";
import LaySidebarFullScreen from "../lay-sidebar/components/SidebarFullScreen.vue";
import Superellipse from "@/components/Superellipse/index.vue";
import BrandLogo from "@/components/BrandLogo/index.vue";

import LogoutCircleRLine from "~icons/ri/logout-circle-r-line";
import Palette from "~icons/ri/palette-line";

const menuRef = ref();
const showLogo = ref(
  storageLocal().getItem<StorageConfigs>(
    `${responsiveStorageNameSpace()}configure`
  )?.showLogo ?? true
);

const {
  route,
  title,
  logout,
  onPanel,
  username,
  userAvatar,
  backTopMenu,
  avatarsStyle
} = useNav();

const defaultActive = computed(() =>
  !isAllEmpty(route.meta?.activePath) ? route.meta.activePath : route.path
);

nextTick(() => {
  menuRef.value?.handleResize();
});

onMounted(() => {
  emitter.on("logoChange", key => {
    showLogo.value = key;
  });
});
</script>

<template>
  <div
    v-loading="usePermissionStoreHook().wholeMenus.length === 0"
    class="horizontal-header"
    :style="{ backgroundColor: 'var(--bg-card)' }"
  >
    <div v-if="showLogo" class="horizontal-header-left" @click="backTopMenu">
      <BrandLogo :size="34" />
      <span class="navbar-brand-name">
        {{ title }}
        <span class="brand-sub">投资账本</span>
        <span class="brand-beta">Beta</span>
      </span>
    </div>
    <el-menu
      ref="menuRef"
      mode="horizontal"
      popper-class="pure-scrollbar"
      class="horizontal-header-menu"
      :default-active="defaultActive"
    >
      <LaySidebarItem
        v-for="route in usePermissionStoreHook().wholeMenus"
        :key="route.path"
        :item="route"
        :base-path="route.path"
      />
    </el-menu>
    <div class="horizontal-header-right">
      <!-- 菜单搜索 -->
      <LaySearch id="header-search" />
      <!-- 全屏 -->
      <LaySidebarFullScreen id="full-screen" />
      <!-- 消息通知 -->
      <LayNotice id="header-notice" />
      <!-- 退出登录 -->
      <el-dropdown trigger="click">
        <span class="el-dropdown-link navbar-bg-hover">
          <Superellipse class="navbar-avatar" :style="avatarsStyle" :power="3">
            <img :src="userAvatar" />
          </Superellipse>
          <p v-if="username" class="dark:text-white">{{ username }}</p>
        </span>
        <template #dropdown>
          <el-dropdown-menu class="logout">
            <el-dropdown-item @click="logout">
              <IconifyIconOffline
                :icon="LogoutCircleRLine"
                style="margin: 5px"
              />
              退出系统
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span
        class="set-icon navbar-bg-hover"
        title="打开外观设置"
        @click="onPanel"
      >
        <IconifyIconOffline :icon="Palette" />
      </span>
    </div>
  </div>
</template>

<style lang="scss" scoped>
:deep(.el-loading-mask) {
  opacity: 0.45;
}

.logout {
  width: 120px;

  ::v-deep(.el-dropdown-menu__item) {
    display: inline-flex;
    flex-wrap: wrap;
    min-width: 100%;
  }
}

/* 品牌文字组：多多贝 + 投资账本副标 + Beta 挂件（与品牌 v1.7、SidebarLogo 一致） */
.horizontal-header-left {
  display: inline-flex;
  gap: 10px;
  align-items: center;
  cursor: pointer;

  .navbar-brand-name {
    display: inline-flex;
    align-items: baseline;
    font-size: 16px;
    font-weight: 600;
    color: var(--el-text-color-primary);

    .brand-sub {
      margin-left: 0.25em;
      font-size: 0.6em;
      font-weight: 400;
      color: var(--el-text-color-secondary);

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
