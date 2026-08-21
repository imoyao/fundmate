<template>
  <div
    class="login-page relative min-h-screen w-full select-none overflow-x-hidden"
  >
    <!-- 深海氛围背景装饰（与登录页同款视觉） -->
    <div
      class="login-bg-decor pointer-events-none fixed inset-0 z-0"
      aria-hidden="true"
    >
      <span class="login-ripple login-ripple--1" />
      <span class="login-ripple login-ripple--2" />
      <span class="login-ripple login-ripple--3" />
      <span class="login-ripple login-ripple--4" />
      <span class="login-bubble login-bubble--1" />
      <span class="login-bubble login-bubble--2" />
      <span class="login-bubble login-bubble--3" />
    </div>

    <div
      class="login-container relative z-10 grid min-h-screen w-full grid-cols-1 min-[969px]:grid-cols-[1.12fr_0.88fr]"
    >
      <!-- 左侧：品牌叙事区（桌面端展示；≤968px 隐藏） -->
      <aside
        class="login-brand relative hidden flex-col overflow-hidden px-10 py-14 min-[969px]:flex xl:px-16"
      >
        <div class="login-brand-bg" v-html="nautilusSvg" />

        <div class="relative z-10 flex items-center gap-3">
          <BrandLogo :size="44" />
          <span class="login-wordmark text-xl font-semibold">
            多多贝
            <span class="login-wordmark-sub ml-2 text-sm font-normal"
              >投资账本</span
            >
          </span>
        </div>

        <div
          class="login-brand-body relative z-10 flex flex-1 flex-col justify-center gap-5"
        >
          <h1
            class="login-slogan max-w-[14ch] text-[clamp(2.2rem,3.4vw,3.1rem)] font-bold leading-[1.15] tracking-[-0.02em]"
          >
            <span class="coral">重置密码</span>
          </h1>
          <p class="login-sub max-w-[30ch] text-base leading-relaxed">
            通过邮件链接安全地设置新密码
          </p>
        </div>

        <p class="login-tagline relative z-10 text-sm">
          潮有涨落，壳有深浅。算得清，才无患。
        </p>
      </aside>

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
              @click="router.replace('/login')"
            >
              返回登录
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { message } from "@/utils/message";
import type { FormInstance, FormRules } from "element-plus";
import BrandLogo from "@/components/BrandLogo/index.vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import nautilusSvg from "@/assets/login/nautilus-light.svg?raw";
import Lock from "~icons/ri/lock-fill";
import { supabase } from "@/utils/supabase";

defineOptions({
  name: "ResetPassword"
});

const router = useRouter();

// 页面状态机：checking（等待链接验证）→ ready（可改密）/ expired（链接无效）
const state = ref<"checking" | "ready" | "expired">("checking");
const loading = ref(false);
const formRef = ref<FormInstance>();

const form = reactive({
  password: "",
  confirmPassword: ""
});

const rules = computed<FormRules>(() => ({
  password: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 8, message: "密码至少 8 位", trigger: "blur" }
  ],
  confirmPassword: [
    { required: true, message: "请确认新密码", trigger: "blur" },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.password) {
          callback(new Error("两次输入的密码不一致"));
        } else {
          callback();
        }
      },
      trigger: "blur"
    }
  ]
}));

let unsubscribe: (() => void) | null = null;
let expireTimer: number | null = null;

onMounted(() => {
  // 邮件链接回跳后 Supabase 自动交换 session 并触发 PASSWORD_RECOVERY 事件
  // （detectSessionInUrl 已开启），不要手动撕 URL 参数
  const { data } = supabase.auth.onAuthStateChange((event, session) => {
    if (event === "PASSWORD_RECOVERY" && session) {
      state.value = "ready";
      if (expireTimer) {
        clearTimeout(expireTimer);
        expireTimer = null;
      }
    }
  });
  unsubscribe = data.subscription.unsubscribe;

  // 兜底：长时间未收到事件 → 链接无效/已过期/已被使用
  expireTimer = window.setTimeout(() => {
    if (state.value === "checking") {
      state.value = "expired";
    }
  }, 30000);
});

onUnmounted(() => {
  unsubscribe?.();
  if (expireTimer) {
    clearTimeout(expireTimer);
  }
});

const onSubmit = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  formEl.validate(async valid => {
    if (!valid) return;
    loading.value = true;
    try {
      const { error } = await supabase.auth.updateUser({
        password: form.password
      });
      if (error) throw error;
      message("密码已重置，请重新登录", { type: "success" });
      // 重置后登出，引导用户用新密码重新登录
      await supabase.auth.signOut();
      router.replace("/login");
    } catch (err: any) {
      message(err.message || "重置失败，请稍后再试", { type: "error" });
    } finally {
      loading.value = false;
    }
  });
};
</script>

<style lang="scss" scoped>
@keyframes bg-breathe {
  0%,
  100% {
    filter: hue-rotate(0deg) saturate(1);
  }

  50% {
    filter: hue-rotate(-4deg) saturate(1.05);
  }
}

@keyframes login-ripple {
  0% {
    opacity: 0.3;
    transform: scale(1) rotate(0deg);
  }

  33% {
    opacity: 0.55;
    transform: scale(1.05) rotate(1deg);
  }

  66% {
    opacity: 0.7;
    transform: scale(1.09) rotate(-0.6deg);
  }

  100% {
    opacity: 0.3;
    transform: scale(1) rotate(0deg);
  }
}

@keyframes login-bubble-rise {
  0%,
  100% {
    opacity: var(--bubble-opacity-min, 0.1);
    transform: translateY(0);
  }

  50% {
    opacity: var(--bubble-opacity-max, 0.2);
    transform: translateY(-40px);
  }
}

@keyframes coral-bob {
  0%,
  100% {
    transform: translateY(0);
  }

  30% {
    transform: translateY(-3px);
  }

  60% {
    transform: translateY(0);
  }
}

@keyframes nautilus-breathe {
  0%,
  100% {
    opacity: var(--nautilus-opacity-min, 0.12);
    transform: translate(-50%, -50%) scale(1) rotate(0deg);
  }

  50% {
    opacity: var(--nautilus-opacity-max, 0.18);
    transform: translate(-50%, -50%) scale(1.06) rotate(3deg);
  }
}

@media (width <= 768px) {
  .login-brand-bg {
    opacity: 0.04;
  }
}

/* ---------- 响应式 ---------- */
@media (width <= 968px) {
  .login-form {
    padding: 0;
    background: transparent;
    border: none;
    box-shadow: none;
  }
}

/* 动效偏好：减弱动态 */
@media (prefers-reduced-motion: reduce) {
  .login-ripple,
  .login-bg-decor,
  .login-brand-bg,
  .login-bubble,
  .coral {
    animation: none;
  }
}

.login-page {
  font-family: var(--font-sans);
  color: var(--text-primary);
  background: linear-gradient(135deg, var(--bg-warm) 0%, var(--bg-page) 60%);
}

/* ---------- 深海氛围背景 ---------- */
.login-bg-decor {
  background: transparent;
  animation: bg-breathe 10s ease-in-out infinite;
}

.login-ripple {
  position: absolute;
  border: 1px solid var(--brand-200);
  border-radius: 50%;
  box-shadow: 0 0 0 6px var(--brand-200);
  animation: login-ripple 9s cubic-bezier(0.45, 0, 0.55, 1) infinite;
}

.login-ripple--1 {
  right: -90px;
  bottom: -100px;
  width: 300px;
  height: 300px;
}

.login-ripple--2 {
  right: -170px;
  bottom: -200px;
  width: 460px;
  height: 460px;
  animation-duration: 13s;
  animation-delay: -2s;
}

.login-ripple--3 {
  right: -250px;
  bottom: -290px;
  width: 640px;
  height: 640px;
  animation-duration: 17s;
  animation-delay: -5s;
}

.login-ripple--4 {
  right: -330px;
  bottom: -390px;
  width: 840px;
  height: 840px;
  animation-duration: 21s;
  animation-delay: -9s;
}

/* 气泡上浮 */
.login-bubble {
  position: absolute;
  pointer-events: none;
  background: var(--brand-700);
  border-radius: 50%;
  animation: login-bubble-rise 8s ease-in-out infinite;
}

.login-bubble--1 {
  top: 20%;
  right: 15%;
  width: 8px;
  height: 8px;
  opacity: 0.15;
}

.login-bubble--2 {
  top: 35%;
  right: 22%;
  width: 5px;
  height: 5px;
  opacity: 0.1;
  animation-duration: 10s;
  animation-delay: 2s;
}

.login-bubble--3 {
  top: 50%;
  right: 12%;
  width: 6px;
  height: 6px;
  opacity: 0.12;
  animation-duration: 9s;
  animation-delay: 4s;
}

/* ---------- 品牌叙事面板 ---------- */
.login-brand {
  position: relative;
  overflow: hidden;
  background: transparent;
}

.login-brand::after {
  position: absolute;
  inset: auto 0 0;
  height: 35%;
  pointer-events: none;
  content: "";
  background: linear-gradient(to top, var(--brand-100), transparent);
  opacity: 0.6;
}

.login-wordmark {
  color: var(--text-primary);
}

.login-wordmark-sub {
  color: var(--text-tertiary);
}

.login-slogan {
  color: var(--text-primary);
}

.coral {
  display: inline-block;
  color: var(--brand-700);
  animation: coral-bob 3.4s ease-in-out infinite;
}

.login-sub {
  color: var(--text-secondary);
}

.login-tagline {
  color: var(--text-tertiary);
  letter-spacing: 0.04em;
}

/* ---------- 品牌视觉锚点（鹦鹉螺插画） ---------- */
.login-brand-bg {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 1;
  width: 80%;
  max-width: 480px;
  height: auto;
  pointer-events: none;
  opacity: var(--nautilus-opacity-min, 0.12);
  transform: translate(-50%, -50%);
  animation: nautilus-breathe 7s cubic-bezier(0.4, 0, 0.6, 1) infinite;

  :deep(svg) {
    width: 100%;
    height: auto;
  }
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

/* 输入框聚焦呼吸 */
:deep(.el-input__wrapper) {
  transition:
    box-shadow 0.4s ease,
    border-color 0.4s ease;

  &.is-focus {
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-700) 12%, transparent);
  }
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
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}

.reset-expired {
  padding: 8px 0;
  text-align: center;
}

/* =====================================================================
   暗色模式独立视觉适配（与登录页同款，design.dark.md v1.5）
   ===================================================================== */

.dark .login-bg-decor {
  background: transparent;
}

.dark .login-ripple {
  border-color: color-mix(in srgb, var(--brand-700) 30%, transparent);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--brand-700) 10%, transparent);
}

.dark .login-bubble {
  --bubble-opacity-min: 0.15;
  --bubble-opacity-max: 0.25;

  background: color-mix(in srgb, var(--brand-700) 60%, transparent);
}

.dark .login-brand {
  background: transparent;
}

.dark .login-brand::after {
  height: 35%;
  background: linear-gradient(
    to top,
    color-mix(in srgb, var(--brand-700) 7%, transparent),
    transparent
  );
  opacity: 0.6;
}

:global(.dark) .login-brand-bg {
  --nautilus-opacity-min: 0.16;
  --nautilus-opacity-max: 0.22;
}

.dark .login-form {
  border-color: var(--border-default);
  box-shadow: var(--shadow-modal);
}

/* =====================================================================
   重置密码页 · 品牌深海鹦鹉螺主题（与登录页同款视觉语言，精简版）
   色值一律取自 design.md 既有令牌（--brand-* / --bg-* / --text-* 等）
   ===================================================================== */
</style>
