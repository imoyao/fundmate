<script setup lang="ts">
import { useNav } from "@/layout/hooks/useNav";
import { useRouter } from "vue-router";
import LaySearch from "../lay-search/index.vue";
import LayNotice from "../lay-notice/index.vue";
import LayNavMix from "../lay-sidebar/NavMix.vue";
import LaySidebarFullScreen from "../lay-sidebar/components/SidebarFullScreen.vue";
import LaySidebarBreadCrumb from "../lay-sidebar/components/SidebarBreadCrumb.vue";
import LaySidebarTopCollapse from "../lay-sidebar/components/SidebarTopCollapse.vue";
import Superellipse from "@/components/Superellipse/index.vue";

// 🆕 新增
import { useTheme } from "@/utils/theme";

import LogoutCircleRLine from "~icons/ri/logout-circle-r-line";
import Palette from "~icons/ri/palette-line";
import UserLine from "~icons/ri/user-3-line";

const {
  layout,
  device,
  logout,
  onPanel,
  pureApp,
  username,
  userAvatar,
  avatarsStyle,
  toggleSideBar
} = useNav();

// 🆕 主题切换
const { isDarkMode, toggleThemeMode } = useTheme();

const router = useRouter();
</script>

<template>
  <div class="navbar" :style="{ backgroundColor: 'var(--bg-card)' }">
    <LaySidebarTopCollapse
      v-if="device === 'mobile'"
      class="hamburger-container"
      :is-active="pureApp.sidebar.opened"
      @toggleClick="toggleSideBar"
    />

    <LaySidebarBreadCrumb
      v-if="layout !== 'mix' && device !== 'mobile'"
      class="breadcrumb-container"
    />

    <LayNavMix v-if="layout === 'mix'" />

    <div v-if="layout === 'vertical'" class="vertical-header-right">
      <!-- 菜单搜索 -->
      <LaySearch id="header-search" />

      <!-- 主题切换快捷按钮（#1842 规则二 A 类）。
           原为 span @click：键盘用户完全用不到主题切换。改真 button 后自带
           可聚焦 / Enter+Space 激活；按钮样式重置用全局工具类 .icon-plain-btn
           （见 style/index.scss），尺寸与配色仍由原有工具类决定。 -->
      <button
        type="button"
        class="icon-plain-btn navbar-bg-hover cursor-pointer px-2 text-base flex items-center"
        :title="isDarkMode ? '切换到亮色模式' : '切换到暗色模式'"
        :aria-label="isDarkMode ? '切换到亮色模式' : '切换到暗色模式'"
        @click="toggleThemeMode"
      >
        <IconifyIconOffline :icon="isDarkMode ? 'ep:sunny' : 'ep:moon'" />
      </button>

      <!-- 全屏 -->
      <LaySidebarFullScreen id="full-screen" />
      <!-- 消息通知 -->
      <LayNotice id="header-notice" />
      <!-- 退出登录 -->
      <el-dropdown trigger="click">
        <span class="el-dropdown-link navbar-bg-hover select-none">
          <Superellipse class="navbar-avatar" :style="avatarsStyle" :power="3">
            <!-- 装饰性头像：用户名就在旁边，alt 留空而不是重复读一遍（#1838） -->
            <img :src="userAvatar" alt="" />
          </Superellipse>
          <p v-if="username" class="dark:text-white">{{ username }}</p>
        </span>
        <template #dropdown>
          <el-dropdown-menu class="logout">
            <el-dropdown-item @click="router.push('/profile')">
              <IconifyIconOffline :icon="UserLine" style="margin: 5px" />
              个人中心
            </el-dropdown-item>
            <el-dropdown-item divided @click="logout">
              <IconifyIconOffline
                :icon="LogoutCircleRLine"
                style="margin: 5px"
              />
              退出系统
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <!-- 外观设置入口（#1842 规则二 A 类）：同上方，span @click → 真 button -->
      <button
        type="button"
        class="icon-plain-btn set-icon navbar-bg-hover"
        title="打开外观设置"
        aria-label="打开外观设置"
        @click="onPanel"
      >
        <IconifyIconOffline :icon="Palette" />
      </button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.navbar {
  width: 100%;
  height: 48px;
  overflow: hidden;

  .hamburger-container {
    float: left;
    height: 100%;
    line-height: 48px;
    cursor: pointer;
  }

  .vertical-header-right {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    min-width: 280px;
    height: 48px;
    color: #000000d9;

    .el-dropdown-link {
      display: flex;
      align-items: center;
      justify-content: space-around;
      height: 48px;
      padding: 10px;
      color: #000000d9;
      cursor: pointer;

      p {
        font-size: 14px;
      }

      /* 头像外框：品牌 n=3 超椭圆（Superellipse 组件承载，勿改回 border-radius 圆形） */
      .navbar-avatar {
        flex-shrink: 0;
        width: 22px;
        height: 22px;

        img {
          display: block;
          width: 100%;
          height: 100%;
        }
      }
    }
  }

  .breadcrumb-container {
    float: left;
    margin-left: 16px;
  }
}

.logout {
  width: 120px;

  ::v-deep(.el-dropdown-menu__item) {
    display: inline-flex;
    flex-wrap: wrap;
    min-width: 100%;
  }
}
</style>
