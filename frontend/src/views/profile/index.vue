<template>
  <div
    class="profile-page min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="profile-head">
      <PageHeaderBar title="个人中心" subtitle="管理账户与安全" />
    </div>

    <div class="profile-shell">
      <!-- ===== 区块一：个人资料 ===== -->
      <ProfileBasicSection :page="profile" />

      <!-- ===== 区块二：账号安全 ===== -->
      <ProfileSecuritySection :page="profile" />
    </div>

    <!-- 改邮箱 / 改密码弹窗（页面级，位于外壳之后） -->
    <ProfileAccountDialogs :page="profile" />
  </div>
</template>

<script setup lang="ts">
import { onActivated } from "vue";
import { useRoute } from "vue-router";
import { useMultiTagsStoreHook } from "@/store/modules/multiTags";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import ProfileBasicSection from "./components/ProfileBasicSection.vue";
import ProfileSecuritySection from "./components/ProfileSecuritySection.vue";
import ProfileAccountDialogs from "./components/ProfileAccountDialogs.vue";
import { useProfileData } from "./composables/useProfileData";

// 个人中心由导航栏头像进入、非侧边菜单点选，页签只能靠组件自身登记
// （/profile 为 hidden 路由不进侧边栏；其余页面由侧边栏 menuSelect → dynamicRouteTag
// 登记，不依赖组件挂载，所以历史上只有本页会出现「进了页面却没有页签」）。
// onActivated 兜底：组件实例若被 keep-alive 复用或挂载时序异常导致 setup 未执行，
// 激活时再补登记——handleTags("push") 幂等（tagHasExits 去重），重复执行无副作用。
// 背景缺陷：后台标签页 rAF 暂停曾把路由视图冻在旧页（setup 压根不执行、页签缺失），
// 根修在 lay-content 的 transitionMain（隐藏时跳过过渡）；此处登记是本页的第二道防线。
const route = useRoute();
const registerTag = () => {
  useMultiTagsStoreHook().handleTags("push", {
    path: route.path,
    name: route.name as string,
    meta: {
      title: route.meta.title || "个人中心",
      ...(route.meta as Record<string, unknown>)
    }
  });
};

registerTag();
onActivated(registerTag);

// 页面状态单体：个人资料 / 账号安全 / 账号弹窗三个子组件注入同一实例（#980 拆分）
const profile = useProfileData();
</script>

<style scoped>
@keyframes fade-up {
  from {
    opacity: 0;
    transform: translateY(24px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ===== 概览页统一卡片与悬停交互 ===== */
.profile-card {
  padding: var(--space-standard);
  background-color: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 16px;
  box-shadow: var(--shadow-raised);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.profile-card:hover {
  box-shadow: var(--shadow-float) !important;
}

.profile-card-enter {
  opacity: 0;
  animation: fade-up 0.6s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

.profile-card-enter:nth-child(1) {
  animation-delay: 0.05s;
}

.profile-card-enter:nth-child(2) {
  animation-delay: 0.1s;
}

/* ===== 页面全局与外壳 ===== */
.profile-page {
  padding: var(--space-5);
}

.profile-head {
  :deep(.page-header) {
    max-width: 680px;
  }

  :deep(.page-header__title) {
    font-size: var(--text-title);
    font-weight: 600;
  }

  :deep(.page-header__subtitle) {
    color: var(--text-tertiary-ink);
  }
}

.profile-shell {
  display: flex;
  flex-direction: column;
  gap: 32px;
  max-width: 680px;
  margin: 0 auto;
}
</style>
