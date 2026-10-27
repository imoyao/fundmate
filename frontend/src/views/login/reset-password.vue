<template>
  <div
    class="login-page relative min-h-screen w-full select-none overflow-x-hidden"
  >
    <!-- 深海氛围背景装饰（与登录页同款视觉），纯 CSS、无交互 -->
    <ResetPasswordBackdrop />

    <div
      class="login-container relative z-10 grid min-h-screen w-full grid-cols-1 min-[969px]:grid-cols-[1.12fr_0.88fr]"
    >
      <!-- 左侧：品牌叙事区（桌面端展示；≤968px 隐藏） -->
      <ResetPasswordBrandAside />

      <!-- 右侧：表单区 -->
      <div
        class="login-box flex items-center justify-center px-4 py-12 max-[968px]:py-10"
      >
        <div class="login-form w-full max-w-[400px]">
          <div class="login-logo flex justify-center">
            <BrandLogo :size="72" />
          </div>

          <h2 class="outline-hidden login-title mb-6 mt-6 text-center">
            重置密码
          </h2>

          <!-- 状态：等待邮件链接验证（PASSWORD_RECOVERY 事件） -->
          <div v-if="state === 'checking'" class="reset-status">
            <el-button
              type="primary"
              size="large"
              loading
              disabled
              class="w-full"
            >
              正在验证链接…
            </el-button>
            <p class="reset-status-tip">请稍候，正在确认你的身份</p>
          </div>

          <!-- 状态：链接有效，可设置新密码 -->
          <el-form
            v-else-if="state === 'ready'"
            ref="formRef"
            :model="form"
            :rules="rules"
            size="large"
            class="w-full"
          >
            <el-form-item prop="password" class="w-full">
              <el-input
                v-model="form.password"
                clearable
                show-password
                placeholder="新密码（至少8位）"
                :prefix-icon="useRenderIcon(Lock)"
              />
            </el-form-item>
            <el-form-item prop="confirmPassword" class="w-full">
              <el-input
                v-model="form.confirmPassword"
                clearable
                show-password
                placeholder="确认新密码"
                :prefix-icon="useRenderIcon(Lock)"
              />
            </el-form-item>
            <el-button
              class="login-submit mt-4! w-full"
              size="large"
              type="primary"
              :loading="loading"
              @click="onSubmit(formRef)"
            >
              重置密码
            </el-button>
          </el-form>

          <!-- 状态：链接无效 / 已过期 -->
          <div v-else class="reset-expired">
            <p class="text-sm" style="color: var(--text-secondary)">
              链接无效或已过期，请重新发起
            </p>
            <el-button
              class="mt-4 w-full"
              size="large"
              @click="$router.replace('/login')"
            >
              返回登录
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<!--
  重置密码页（#980 批 B7 拆分后只剩「外壳 + 三态表单」）

  拆分前的三块各自独立，已分别抽出：
  - 深海背景装饰（4 圈涟漪 + 3 颗气泡 + 5 组 keyframes）→ `ResetPasswordBackdrop`
  - 左侧品牌叙事区（鹦鹉螺插画 + 标题 / 副标题 / 落款）→ `ResetPasswordBrandAside`
  - 状态机 / 表单校验 / 提交（含错误文案中文化）→ `composables/useResetPassword`

  留在本文件的是「两列 grid 外壳」与三态表单。表单没有单独成组件，因为它
  依赖 `useResetPassword` 的状态与 `formRef`，且样式末尾那条 968px 媒体查询与模板里的
  `max-[968px]:` 是**成对**的（`guard_breakpoints.py` 的存量基线按「文件::媒体条件」
  记账，搬到子组件会让基线对不上）。
-->

<script setup lang="ts">
import BrandLogo from "@/components/BrandLogo/index.vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import Lock from "~icons/ri/lock-fill";
import ResetPasswordBackdrop from "./components/ResetPasswordBackdrop.vue";
import ResetPasswordBrandAside from "./components/ResetPasswordBrandAside.vue";
import { useResetPassword } from "./composables/useResetPassword";

defineOptions({
  name: "ResetPassword"
});

// 状态机 / 表单校验 / 提交（含错误文案中文化）见 composable，页面只留编排
const { state, loading, formRef, form, rules, onSubmit } = useResetPassword();
</script>

<style lang="scss" scoped>
.login-page {
  font-family: var(--font-sans);
  color: var(--text-primary);
  background: linear-gradient(135deg, var(--bg-warm) 0%, var(--bg-page) 60%);
}

/* ---------- 表单卡片 ---------- */
.login-form {
  padding: var(--space-loose);
  background: var(--bg-card);
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

/* 提交按钮果冻弹性（与登录页一致） */
.login-submit {
  transition:
    transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1),
    background-color 0.2s ease,
    border-color 0.2s ease;

  &:hover:not(:disabled) {
    transform: scale(1.02);
  }

  &:active:not(:disabled) {
    transform: scale(0.97);
  }
}

/* 输入框聚焦呼吸：**只放慢过渡**（0.4s），焦点表达式本身用 element-plus.scss
   「输入基线」的默认值。#1815 起基线默认即「1px 品牌内描边 + 3px 12% 柔光」的
   轻聚焦单环，本文件原先复制了同一份表达式，属重复维护，已删除。 */
.el-form {
  --input-transition: box-shadow 0.4s ease;
}

/* 浏览器自动填充背景覆盖（与登录页同一处理）。
   注：部分新浏览器对 box-shadow inset 覆盖 autofill 背景的旧技巧已不完全生效
   （会漏出浅蓝底色），故追加 background-color: transparent 与
   background-clip: content-box 兜底：前者直接置透明，后者把背景裁剪到内容盒
   （避免 padding 区域残留色块），双保险覆盖 autofill 底色。 */
:deep(input:-webkit-autofill),
:deep(input:-webkit-autofill:hover),
:deep(input:-webkit-autofill:focus),
:deep(input:-webkit-autofill:active) {
  caret-color: var(--text-primary);
  background-color: transparent !important;
  background-clip: content-box !important;
  box-shadow: 0 0 0 1000px var(--bg-card) inset !important;
  -webkit-text-fill-color: var(--text-primary) !important;
}

/* 状态提示区 */
.reset-status-tip {
  margin-top: 12px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;
}

.reset-expired {
  padding: 8px 0;
  text-align: center;
}

.dark .login-form {
  border-color: var(--border-default);
  box-shadow: var(--shadow-modal);
}

/* ============ 响应式 ============
   ⚠️ 这条原先排在基础声明**之前**，覆盖被后面同选择器的声明压掉、**从未生效**
   （2026-09-18 修复，见 #1576 同类台账）。现在它排在 `.login-form` 基础声明之后。 */

/* 移动端表单卡片回归「页面本体」；阈值与模板的 `max-[968px]:` / `min-[969px]:` 成对 */
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
