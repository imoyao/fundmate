<template>
  <!-- 右侧：表单区 -->
  <div
    class="login-box flex items-center justify-center px-4 py-12 max-[968px]:py-10"
  >
    <div class="login-form w-full max-w-[400px]">
      <!-- 移动端品牌 Slogan（≤968px 显示在表单上方） -->
      <div class="login-mobile-brand mb-6 hidden max-[968px]:block">
        <h1 class="text-[1.55rem] font-bold leading-tight tracking-[-0.01em]">
          看见你的<span class="coral">复利曲线</span>
        </h1>
        <p class="login-sub mt-2 text-sm">一个让复利曲线清晰可见的投资账本</p>
      </div>

      <div class="login-logo flex justify-center">
        <BrandLogo :size="72" />
      </div>

      <Motion class="w-full">
        <h2 class="outline-hidden login-title mb-6 text-center">
          {{ p.isRegisterMode ? "创建账户" : "欢迎回来" }}
        </h2>
      </Motion>
      <LoginFormFields :page="page" />
      <!-- 切换登录/注册 -->
      <div class="flex justify-center mt-4">
        <span class="text-sm" style="color: var(--text-secondary)">
          {{ p.isRegisterMode ? "已有账户？" : "还没有账户？" }}
          <el-link type="primary" @click="p.toggleMode">
            {{ p.isRegisterMode ? "去登录" : "立即注册" }}
          </el-link>
        </span>
      </div>

      <!-- GitHub 登录（跨子域 SSO 共用同一 Supabase 项目） -->
      <el-divider v-if="!p.isRegisterMode" class="login-divider">
        <span class="text-xs" style="color: var(--text-tertiary-ink)"
          >其他登录方式</span
        >
      </el-divider>
      <el-button
        v-if="!p.isRegisterMode"
        class="login-github w-full"
        size="large"
        :loading="p.githubLoading"
        @click="p.onGithubLogin"
      >
        <span class="flex items-center justify-center gap-2">
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              d="M12 .5C5.37.5 0 5.87 0 12.5c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58v-2.03c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.09-.75.08-.73.08-.73 1.2.09 1.84 1.24 1.84 1.24 1.07 1.84 2.81 1.31 3.5 1 .11-.78.42-1.31.76-1.61-2.67-.3-5.47-1.34-5.47-5.95 0-1.31.47-2.39 1.24-3.23-.12-.3-.54-1.53.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6.01 0c2.29-1.55 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.77.84 1.23 1.92 1.23 3.23 0 4.62-2.81 5.64-5.49 5.94.43.37.81 1.1.81 2.22v3.29c0 .32.22.7.83.58A12.01 12.01 0 0 0 24 12.5C24 5.87 18.63.5 12 .5Z"
            />
          </svg>
          <span>使用 GitHub 登录</span>
        </span>
      </el-button>

      <!-- 登录提示 -->
      <div v-if="!p.isRegisterMode" class="login-hint mt-3">
        <span class="text-xs" style="color: var(--text-tertiary-ink)">
          使用邮箱或用户名登录
        </span>
      </div>

      <!-- 注册成功提示 -->
      <div
        v-if="!p.isRegisterMode && p.showRegisterSuccess"
        class="register-success mt-3"
      >
        <el-alert
          title="注册成功！请查收验证邮件激活账户"
          type="success"
          :closable="false"
          show-icon
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import Motion from "../utils/motion";
import BrandLogo from "@/components/BrandLogo/index.vue";
import LoginFormFields from "./LoginFormFields.vue";
import type { useLogin } from "../composables/useLogin";

defineOptions({ name: "LoginFormPanel" });

const props = defineProps<{ page: ReturnType<typeof useLogin> }>();

/**
 * 共享状态单体（useLogin）的响应式视图（#980 P1-C，P1-A/B 同款）：
 * reactive 会解包嵌套 ref，模板内可直接读值、写回同一实例。
 */
const p = reactive(props.page);
</script>

<style lang="scss" scoped>
/* ---------- 表单卡片 ---------- */
.login-form {
  padding: var(--space-loose);
  background: var(--bg-card);

  /* 半透明细边框 + 品牌色柔影，替代硬边框，弱化"独立卡片"感 */
  border: 1px solid color-mix(in srgb, var(--border-light) 60%, transparent);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 32px -8px
    color-mix(in srgb, var(--brand-700) 8%, transparent);
}

.login-title {
  font-size: var(--text-title);
  font-weight: 500;
  color: var(--text-primary);
  letter-spacing: 0.01em;
}

.login-mobile-brand h1 {
  color: var(--text-primary);
}

/* .coral / .login-sub：品牌叙事区与移动端 Slogan 共用类，拆分后本组件自持一份
   （原文件单点样式作用于两处；reset-password.vue 已有同款复制先例） */
.coral {
  color: var(--brand-700);
}

.login-sub {
  color: var(--text-secondary);
}

.dark .login-form {
  /* 暗色下阴影 token 已是"内阴影提亮 + 深投影"（design.dark.md Elevation），
     保留以维持卡片层次；边框用提亮边框而非亮色浅边框 */
  border-color: var(--border-default);
  box-shadow: var(--shadow-modal);
}

/* 分割线文字/边框颜色对齐品牌令牌 */
.login-divider {
  --el-divider-text-color: var(--text-tertiary);
  --el-divider-border-color: var(--border-light);
}

/* GitHub 登录按钮：消除相邻按钮默认 margin */
.login-github {
  margin-left: 0;
}

.login-hint {
  text-align: center;
}

.register-success {
  margin-top: 12px;
}

/* 移动端表单卡片回归「页面本体」，去掉卡片化包装。
   阈值保持 968px：它与模板里的 `max-[968px]:` / `min-[969px]:` 是**成对**的，
   改走 Tailwind 档会让 SCSS 与 class 分叉（那正是 #1571 要避免的事）。 */
@media (width <= 968px) /* breakpoint-allow: 与模板 max-[968px] 配对 */ {
  /* 说明（已上移到 @media 同行）：与模板任意值断点 max-[968px] 配对 */
  .login-form {
    padding: 0;
    background: transparent;
    border: none;
    box-shadow: none;
  }
}
</style>
