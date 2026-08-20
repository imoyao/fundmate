<template>
  <div
    class="login-page relative min-h-screen w-full select-none overflow-x-hidden"
  >
    <!-- 深海氛围背景装饰（纯 CSS 实现，替代原 bg.png 波浪图；不引入图片资源） -->
    <div
      class="login-bg-decor pointer-events-none fixed inset-0 z-0"
      aria-hidden="true"
    >
      <span class="login-ripple login-ripple--1" />
      <span class="login-ripple login-ripple--2" />
      <span class="login-ripple login-ripple--3" />
      <span class="login-ripple login-ripple--4" />
    </div>

    <!-- 亮暗切换 -->
    <div class="flex-c absolute right-5 top-3 z-30">
      <el-switch
        v-model="dataTheme"
        inline-prompt
        :active-icon="dayIcon"
        :inactive-icon="darkIcon"
        @change="dataThemeChange"
      />
    </div>

    <div
      class="login-container relative z-10 grid min-h-screen w-full grid-cols-1 min-[969px]:grid-cols-[1.12fr_0.88fr]"
    >
      <!-- 左侧：品牌叙事区（桌面端展示；≤968px 隐藏，与旧插画区同策略） -->
      <aside
        class="login-brand relative hidden flex-col overflow-hidden px-10 py-14 min-[969px]:flex xl:px-16"
      >
        <!-- 背景装饰层：鹦鹉螺插画全幅半透明，文字浮于其上 -->
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
            看见你的<span class="coral">复利曲线</span>
          </h1>
          <p class="login-sub max-w-[30ch] text-base leading-relaxed">
            一个让复利曲线清晰可见的投资账本
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
          <!-- 移动端品牌 Slogan（≤968px 显示在表单上方） -->
          <div class="login-mobile-brand mb-6 hidden max-[968px]:block">
            <h1
              class="text-[1.55rem] font-bold leading-tight tracking-[-0.01em]"
            >
              看见你的<span class="coral">复利曲线</span>
            </h1>
            <p class="login-sub mt-2 text-sm">
              一个让复利曲线清晰可见的投资账本
            </p>
          </div>

          <div class="login-logo flex justify-center">
            <BrandLogo :size="72" />
          </div>

          <Motion class="w-full">
            <h2 class="outline-hidden login-title mb-6 text-center">
              {{ isRegisterMode ? "创建账户" : "欢迎回来" }}
            </h2>
          </Motion>

          <!--
            输入框宽度对齐（根因修复）：
            el-form-item 默认按内容收缩（shrink-to-fit）而非撑满父级，
            注册模式字段更多、内容各异时各输入框宽度会不一致。
            修法：Motion 包裹层与每个 el-form-item 都显式 w-full（width:100%），
            其内部 flex 子项（el-input 等）随 stretch 拉伸到等宽。
          -->
          <el-form
            ref="ruleFormRef"
            :model="ruleForm"
            :rules="isRegisterMode ? registerRules : loginRules"
            size="large"
            class="w-full"
          >
            <!-- 邮箱 / 用户名（登录模式二选一） -->
            <Motion class="w-full" :delay="100">
              <el-form-item prop="email" class="w-full">
                <el-input
                  v-model="ruleForm.email"
                  clearable
                  :placeholder="isRegisterMode ? '邮箱地址' : '邮箱或用户名'"
                  :prefix-icon="useRenderIcon(User)"
                />
              </el-form-item>
            </Motion>

            <!-- 昵称（仅注册模式） -->
            <Motion v-if="isRegisterMode" class="w-full" :delay="150">
              <el-form-item prop="username" class="w-full">
                <el-input
                  v-model="ruleForm.username"
                  clearable
                  maxlength="16"
                  placeholder="昵称（用于展示）"
                  :prefix-icon="useRenderIcon(User)"
                />
              </el-form-item>
            </Motion>

            <!-- 密码 -->
            <Motion class="w-full" :delay="200">
              <el-form-item prop="password" class="w-full">
                <el-input
                  v-model="ruleForm.password"
                  clearable
                  show-password
                  placeholder="密码（至少8位）"
                  :prefix-icon="useRenderIcon(Lock)"
                />
              </el-form-item>
              <!-- 忘记密码（仅登录模式）：右对齐小链接，与切换/隐私政策链接同风格 -->
              <div v-if="!isRegisterMode" class="login-forgot flex justify-end">
                <el-link type="primary" @click="openForgotDialog"
                  >忘记密码？</el-link
                >
              </div>
            </Motion>

            <!-- 确认密码（仅注册模式） -->
            <Motion v-if="isRegisterMode" class="w-full" :delay="250">
              <el-form-item prop="confirmPassword" class="w-full">
                <el-input
                  v-model="ruleForm.confirmPassword"
                  clearable
                  show-password
                  placeholder="确认密码"
                  :prefix-icon="useRenderIcon(Lock)"
                />
              </el-form-item>
            </Motion>

            <!-- 隐私政策（仅注册模式） -->
            <Motion v-if="isRegisterMode" class="w-full" :delay="300">
              <el-form-item prop="agreePolicy" class="w-full">
                <div class="privacy-policy-wrapper">
                  <el-checkbox
                    v-model="ruleForm.agreePolicy"
                    class="privacy-checkbox"
                  />
                  <span class="privacy-text">
                    我已阅读并同意
                    <el-link type="primary" @click="openPrivacyPolicy"
                      >《隐私政策》</el-link
                    >
                    <span class="privacy-separator">·</span>
                    <el-link type="primary" @click="openTerms"
                      >《服务条款》</el-link
                    >
                  </span>
                </div>
              </el-form-item>
            </Motion>

            <!-- 提交按钮（size=large 与 40px 输入框等高，避免 :deep 改组件内部样式） -->
            <Motion class="w-full" :delay="isRegisterMode ? 350 : 250">
              <el-button
                class="login-submit mt-4! w-full"
                size="large"
                type="primary"
                :loading="loading"
                :disabled="disabled"
                @click="onSubmit(ruleFormRef)"
              >
                {{ isRegisterMode ? "注册" : "登录" }}
              </el-button>
            </Motion>
          </el-form>

          <!-- 切换登录/注册 -->
          <div class="flex justify-center mt-4">
            <span class="text-sm" style="color: var(--text-secondary)">
              {{ isRegisterMode ? "已有账户？" : "还没有账户？" }}
              <el-link type="primary" @click="toggleMode">
                {{ isRegisterMode ? "去登录" : "立即注册" }}
              </el-link>
            </span>
          </div>

          <!-- GitHub 登录（跨子域 SSO 共用同一 Supabase 项目） -->
          <el-divider v-if="!isRegisterMode" class="login-divider">
            <span class="text-xs" style="color: var(--text-tertiary)"
              >其他登录方式</span
            >
          </el-divider>
          <el-button
            v-if="!isRegisterMode"
            class="login-github w-full"
            size="large"
            :loading="githubLoading"
            @click="onGithubLogin"
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
          <div v-if="!isRegisterMode" class="login-hint mt-3">
            <span class="text-xs" style="color: var(--text-tertiary)">
              使用邮箱或用户名登录
            </span>
          </div>

          <!-- 注册成功提示 -->
          <div
            v-if="!isRegisterMode && showRegisterSuccess"
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
    </div>

    <!-- 忘记密码弹窗：收集邮箱发起重置邮件（防用户枚举，统一提示已发送） -->
    <el-dialog
      v-model="forgotVisible"
      title="重置密码"
      width="min(400px, calc(100vw - 32px))"
      :close-on-click-modal="false"
      append-to-body
      class="login-forgot-dialog"
    >
      <el-form
        ref="forgotFormRef"
        :model="forgotForm"
        :rules="forgotRules"
        size="large"
      >
        <el-form-item prop="email" class="w-full">
          <el-input
            v-model="forgotForm.email"
            clearable
            placeholder="请输入注册邮箱"
            :prefix-icon="useRenderIcon(User)"
            @keyup.enter="onForgotSubmit(forgotFormRef)"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="forgotVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="forgotLoading"
          @click="onForgotSubmit(forgotFormRef)"
        >
          发送重置邮件
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import Motion from "./utils/motion";
import { useRouter } from "vue-router";
import { message } from "@/utils/message";
import { ref, reactive, computed } from "vue";
import { debounce } from "@pureadmin/utils";
import { useEventListener } from "@vueuse/core";
import type { FormInstance, FormRules } from "element-plus";
import { useLayout } from "@/layout/hooks/useLayout";
import { initRouter } from "@/router/utils";
import BrandLogo from "@/components/BrandLogo/index.vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";

import dayIcon from "@/assets/svg/day.svg?component";
import darkIcon from "@/assets/svg/dark.svg?component";
import nautilusSvg from "@/assets/login/nautilus-light.svg?raw";
import Lock from "~icons/ri/lock-fill";
import User from "~icons/ri/user-3-fill";

import { supabase } from "@/utils/supabase";
import { resolveIdentifier } from "@/api/auth";

defineOptions({
  name: "Login"
});

const router = useRouter();
const loading = ref(false);
const disabled = ref(false);
const githubLoading = ref(false);
const ruleFormRef = ref<FormInstance>();
const isRegisterMode = ref(false);
const showRegisterSuccess = ref(false);

const { initStorage } = useLayout();
initStorage();

const { dataTheme, overallStyle, dataThemeChange } = useDataThemeChange();
dataThemeChange(overallStyle.value);

// ============================================
// 表单数据
// ============================================
const ruleForm = reactive({
  email: "",
  username: "",
  password: "",
  confirmPassword: "",
  agreePolicy: false
});

// ============================================
// 登录验证规则
// ============================================
const loginRules = computed<FormRules>(() => ({
  // 登录模式：该字段接受"邮箱 或 用户名"，故不做邮箱格式强校验，仅要求非空
  email: [{ required: true, message: "请输入邮箱或用户名", trigger: "blur" }],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 8, message: "密码至少 8 位", trigger: "blur" }
  ]
}));

// ============================================
// 注册验证规则
// ============================================
const registerRules = computed<FormRules>(() => ({
  email: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    { type: "email", message: "请输入有效的邮箱地址", trigger: "blur" }
  ],
  username: [
    { required: true, message: "请输入昵称", trigger: "blur" },
    { min: 5, max: 16, message: "昵称长度 5-16 个字符", trigger: "blur" },
    {
      pattern: /^[\u4e00-\u9fa5a-zA-Z0-9_]+$/,
      message: "昵称只能包含中文、字母、数字和下划线",
      trigger: "blur"
    }
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 8, message: "密码至少 8 位", trigger: "blur" }
  ],
  confirmPassword: [
    { required: true, message: "请确认密码", trigger: "blur" },
    {
      validator: (_rule, value, callback) => {
        if (value !== ruleForm.password) {
          callback(new Error("两次输入的密码不一致"));
        } else {
          callback();
        }
      },
      trigger: "blur"
    }
  ],
  agreePolicy: [
    {
      validator: (_rule, value, callback) => {
        if (!value) {
          callback(new Error("请阅读并同意隐私政策"));
        } else {
          callback();
        }
      },
      trigger: "change"
    }
  ]
}));

// ============================================
// 切换模式
// ============================================
const toggleMode = () => {
  isRegisterMode.value = !isRegisterMode.value;
  showRegisterSuccess.value = false;
  ruleForm.email = "";
  ruleForm.username = "";
  ruleForm.password = "";
  ruleForm.confirmPassword = "";
  ruleForm.agreePolicy = false;
};

// ============================================
// 打开隐私政策
// ============================================
const openPrivacyPolicy = () => {
  window.open("/privacy", "_blank");
};

const openTerms = () => {
  window.open("/terms", "_blank");
};

// ============================================
// GitHub OAuth 登录（跨子域 SSO）
// ============================================
const onGithubLogin = async () => {
  githubLoading.value = true;
  try {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "github",
      options: {
        // 回调落回本站根路径即可：应用站是 hash 模式，若直接写 /welcome
        // 会被 Supabase 编码成 ?redirect_to=/welcome 塞进 hash，变成
        // welcome#/welcome 导致无法正确匹配路由。回到根后由路由守卫
        // getSession() 识别已登录态，自动 redirect 到 /welcome 概览页。
        redirectTo: `${window.location.origin}/`
      }
    });
    if (error) throw error;
    // 成功时 Supabase 会重定向到 GitHub，无需手动处理
  } catch (err: any) {
    message(err.message || "GitHub 登录失败，请稍后再试", { type: "error" });
    githubLoading.value = false;
  }
};

// ============================================
// 忘记密码（防用户枚举：邮箱不存在也返回成功，前端一律提示"已发送"）
// ============================================
const forgotVisible = ref(false);
const forgotLoading = ref(false);
const forgotFormRef = ref<FormInstance>();
const forgotForm = reactive({ email: "" });

const forgotRules = computed<FormRules>(() => ({
  email: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    { type: "email", message: "请输入有效的邮箱地址", trigger: "blur" }
  ]
}));

const openForgotDialog = () => {
  forgotForm.email = "";
  forgotVisible.value = true;
  // 清空上次校验状态，避免弹窗复用时残留飘红
  forgotFormRef.value?.clearValidate();
};

const onForgotSubmit = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  formEl.validate(async valid => {
    if (!valid) return;
    forgotLoading.value = true;
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(
        forgotForm.email.trim(),
        {
          // 同源回跳路径：规避 PKCE code_verifier 跨域丢失；
          // 回跳后由 onAuthStateChange 的 PASSWORD_RECOVERY 事件接管（detectSessionInUrl 已开）
          redirectTo: `${window.location.origin}/reset-password`
        }
      );
      if (error) throw error;
      // 防用户枚举：不区分邮箱是否存在，统一提示已发送
      message("重置邮件已发送，请查收邮箱", { type: "success" });
      forgotVisible.value = false;
    } catch (err: any) {
      message(err.message || "发送失败，请稍后再试", { type: "error" });
    } finally {
      forgotLoading.value = false;
    }
  });
};

// ============================================
// 提交表单
// ============================================
const onSubmit = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;

  formEl.validate(async valid => {
    if (!valid) return;

    loading.value = true;
    disabled.value = true;

    try {
      if (isRegisterMode.value) {
        // 🔥 注册
        const { data, error } = await supabase.auth.signUp({
          email: ruleForm.email.trim(),
          password: ruleForm.password,
          options: {
            // 邮箱验证回调同样回根路径，由前端守卫接管跳转，避免 hash 模式编码异常
            emailRedirectTo: `${window.location.origin}/`,
            data: {
              username: ruleForm.username.trim()
            }
          }
        });

        if (error) throw error;

        showRegisterSuccess.value = true;
        message("注册成功！请查收验证邮件", { type: "success" });
        // 切换到登录模式
        setTimeout(() => {
          isRegisterMode.value = false;
          showRegisterSuccess.value = false;
          ruleForm.password = "";
          ruleForm.confirmPassword = "";
          ruleForm.agreePolicy = false;
        }, 2000);
      } else {
        // 🔥 登录：标识可能是邮箱或用户名，先解析为规范邮箱再做密码登录（D10）
        const raw = ruleForm.email.trim();
        let email = raw;
        if (!raw.includes("@")) {
          const { data: resolveData } = await resolveIdentifier(raw);
          email = resolveData?.email ?? "";
          if (!email) {
            throw new Error("未找到该用户名对应的账户");
          }
        }
        const { data, error } = await supabase.auth.signInWithPassword({
          email,
          password: ruleForm.password
        });

        if (error) throw error;

        message("登录成功", { type: "success" });
        await initRouter();
        router.push("/welcome");
      }
    } catch (err: any) {
      message(err.message || "操作失败，请重试", { type: "error" });
    } finally {
      disabled.value = false;
      loading.value = false;
    }
  });
};

// ============================================
// 回车键提交
// ============================================
const immediateDebounce: any = debounce(
  formRef => onSubmit(formRef),
  1000,
  true
);

useEventListener(document, "keydown", ({ code }) => {
  if (
    ["Enter", "NumpadEnter"].includes(code) &&
    !disabled.value &&
    !loading.value
  ) {
    immediateDebounce(ruleFormRef.value);
  }
});
</script>

<style lang="scss" scoped>
/* 背景角度注册为可插值属性（Chrome/Safari 111+；不支持时渐变按 135deg 静态显示，安全降级） */
@property --bg-angle {
  syntax: "<angle>";
  initial-value: 135deg;
  inherits: false;
}

@keyframes login-bg-breathe {
  0%,
  100% {
    --bg-angle: 135deg;
  }

  50% {
    --bg-angle: 145deg;
  }
}

@keyframes login-ripple {
  /* 有机呼吸环：不等比缩放 + 微旋转，像水面涟漪自然扩散而非死板同心缩放 */
  0% {
    opacity: 0.28;
    transform: scale(1) rotate(0deg);
  }

  33% {
    opacity: 0.5;
    transform: scale(1.03) rotate(0.5deg);
  }

  66% {
    opacity: 0.65;
    transform: scale(1.06) rotate(-0.3deg);
  }

  100% {
    opacity: 0.28;
    transform: scale(1) rotate(0deg);
  }
}

@keyframes login-curve-bob {
  0%,
  100% {
    transform: translateY(0) rotate(0deg);
  }

  15% {
    transform: translateY(-4px) rotate(-2deg);
  }

  32% {
    transform: translateY(0) rotate(0deg);
  }

  46% {
    transform: translateY(-2px) rotate(1deg);
  }

  60% {
    transform: translateY(0) rotate(0deg);
  }
}

@keyframes nautilus-breathe {
  0%,
  100% {
    opacity: var(--nautilus-opacity-min, 0.08);
    transform: translate(-50%, -50%) scale(1) rotate(0deg);
  }

  50% {
    opacity: var(--nautilus-opacity-max, 0.12);
    transform: translate(-50%, -50%) scale(1.03) rotate(2deg);
  }
}

/* 移动端：品牌区仅剩 logo+名称，插画进一步压淡（防御性，<969px 时 aside 已隐藏） */
@media (width <= 768px) {
  .login-brand-bg {
    opacity: 0.04;
  }
}

/* ---------- 响应式 ---------- */
@media (width <= 968px) {
  /* 移动端表单卡片回归"页面本体"，去掉卡片化包装 */
  .login-form {
    padding: 0;
    background: transparent;
    border: none;
    box-shadow: none;
  }
}

@media (width <= 480px) {
  .privacy-policy-wrapper {
    align-items: flex-start;

    .privacy-checkbox {
      margin-top: 2px;
    }

    .privacy-text {
      font-size: 13px;
    }
  }
}

/* 动效偏好：减弱动态 */
@media (prefers-reduced-motion: reduce) {
  .login-ripple,
  .coral-curve,
  .login-page,
  .login-brand-bg {
    animation: none;
  }
}

.login-page {
  font-family: var(--font-sans);
  color: var(--text-primary);

  /* 统一连续背景：左侧暖奶油 → 右侧浅灰水平渐变，弱化左右分界 */
  background: linear-gradient(
    var(--bg-angle, 135deg),
    var(--bg-warm) 0%,
    var(--bg-page) 60%
  );

  /* 背景"呼吸"：角度缓慢摆动，让色彩流动起来 */
  animation: login-bg-breathe 12s ease-in-out infinite;
}

/* ---------- 深海氛围背景（CSS 装饰，替代原 bg.png 波浪图） ---------- */
.login-bg-decor {
  /* 统一背景后改透明：页面渐变由 .login-page 提供，本层只承载涟漪装饰 */
  background: transparent;
}

.login-ripple {
  position: absolute;
  border: 1px solid var(--brand-200);
  border-radius: 50%;

  /* 柔和扩散环：细边框 + 外扩光晕，替代单一硬线 */
  box-shadow: 0 0 0 6px var(--brand-200);

  /* 每环独立周期 + 负延迟错相，形成"深海呼吸"的错落感而非同步跳动 */
  animation: login-ripple 11s cubic-bezier(0.45, 0, 0.55, 1) infinite;
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
  animation-duration: 15s;
  animation-delay: -3s;
}

.login-ripple--3 {
  right: -250px;
  bottom: -290px;
  width: 640px;
  height: 640px;
  animation-duration: 19s;
  animation-delay: -7s;
}

.login-ripple--4 {
  right: -330px;
  bottom: -390px;
  width: 840px;
  height: 840px;
  animation-duration: 24s;
  animation-delay: -12s;
}

/* ---------- 品牌叙事面板 ---------- */
.login-brand {
  position: relative;
  overflow: hidden;

  /* 去掉独立渐变：与 .login-page 共享连续背景，弱化左右分界 */
  background: transparent;
}

.login-brand::after {
  position: absolute;
  inset: auto 0 0;
  height: 35%;
  pointer-events: none;

  /* 底部过渡晕染（调淡）：作为左右交界处的自然过渡 */
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
  color: var(--brand-700);
}

.coral-curve {
  display: inline-block;
  transform-origin: 50% 85%;
  animation: login-curve-bob 3.4s ease-in-out infinite;
}

.login-sub {
  color: var(--text-secondary);
}

.login-tagline {
  color: var(--text-tertiary);
  letter-spacing: 0.04em;
}

/* ---------- 品牌视觉锚点（鹦鹉螺插画：全幅半透明背景装饰层） ---------- */
.login-brand-bg {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 1;
  width: 80%;
  max-width: 480px;
  height: auto;
  pointer-events: none;

  /* 呼吸脉动：scale + opacity 起伏 + 极慢微旋转（深海中的鹦鹉螺） */
  opacity: var(--nautilus-opacity-min, 0.08);
  transform: translate(-50%, -50%);
  animation: nautilus-breathe 8s cubic-bezier(0.4, 0, 0.6, 1) infinite;

  :deep(svg) {
    width: 100%;
    height: auto;
  }
}

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

/* 提交按钮果冻弹性：hover 微弹起，active 按下回弹（弹性曲线） */
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

/* 输入框聚焦呼吸：柔和品牌色光晕替代默认硬描边 */
:deep(.el-input__wrapper) {
  transition:
    box-shadow 0.4s ease,
    border-color 0.4s ease;

  &.is-focus {
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-700) 12%, transparent);
  }
}

/* 浏览器自动填充背景覆盖：清除 Chrome 默认浅蓝底色，
   避免与左右图标容器形成「白-蓝-白」三明治（与 reset-password.vue 同一处理） */
::deep(input:-webkit-autofill),
::deep(input:-webkit-autofill:hover),
::deep(input:-webkit-autofill:focus),
::deep(input:-webkit-autofill:active) {
  caret-color: var(--text-primary);
  box-shadow: 0 0 0 1000px var(--bg-card) inset !important;
  -webkit-text-fill-color: var(--text-primary) !important;
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

/* =====================================================================
   暗色模式独立视觉适配（design.dark.md v1.5）
   - 亮色渐变里的 --brand-100/--brand-200 在暗色下是深棕（#2d1612/#3d1c17），
     直接沿用会糊成一团；暗色下改用"深灰底 + 品牌色低透明度光晕"，
     品牌色饱和度已由 dark.scss 降 20%（--brand-700 → #d45a44）。
   - 低透明度光晕用 color-mix(in srgb, var(--brand-700) x%, transparent)
     实现（等价于 rgba(var(--brand-700-rgb), x) 手法，项目无 -rgb 变量；
     需 Chrome 111+，与 design.dark.md 接受的 hsl(from) 现代语法同级）。
   - 发光仅用于静止/呼吸装饰，遵守 design.dark.md「禁止动画循环中发光」
     性能红线——涟漪/光环用低透明度边框与扩散环表达，不用 box-shadow 辉光。
   ===================================================================== */

.dark .login-bg-decor {
  background: transparent;
}

.dark .login-ripple {
  border-color: color-mix(in srgb, var(--brand-700) 30%, transparent);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--brand-700) 10%, transparent);
}

.dark .login-brand {
  /* 与亮色一致：去掉独立渐变，共享 .login-page 连续背景 */
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

/* 暗色下插画呼吸范围提亮：0.12 ~ 0.16（动画 opacity 用 CSS 变量控制） */
:global(.dark) .login-brand-bg {
  --nautilus-opacity-min: 0.12;
  --nautilus-opacity-max: 0.16;
}

.dark .login-form {
  /* 暗色下阴影 token 已是"内阴影提亮 + 深投影"（design.dark.md Elevation），
     保留以维持卡片层次；边框用提亮边框而非亮色浅边框 */
  border-color: var(--border-default);
  box-shadow: var(--shadow-modal);
}

/* ---------- 表单内辅助样式 ---------- */

/* 隐私政策 */
.privacy-policy-wrapper {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 0;
  user-select: none;

  .privacy-checkbox {
    flex-shrink: 0;
    margin-right: 0;
  }

  .privacy-text {
    font-size: 14px;
    line-height: 1.5;
    color: var(--text-secondary);

    .el-link {
      padding: 0 2px;
      font-size: 14px;
      vertical-align: baseline;
    }

    .privacy-separator {
      margin: 0 4px;
      color: var(--border-default);
    }
  }
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

/* 忘记密码链接：右对齐小链接，与切换/隐私政策链接同风格 */
.login-forgot {
  margin-top: 2px;
}

.login-forgot .el-link {
  font-size: 13px;
}

/* 忘记密码弹窗：对齐登录卡片视觉（半透明边框 + 品牌柔影） */
:global(.login-forgot-dialog) {
  --el-dialog-bg-color: var(--bg-card);
  --el-dialog-border-radius: var(--radius-lg);

  border: 1px solid color-mix(in srgb, var(--brand-700) 18%, transparent);
  box-shadow: 0 8px 32px -8px
    color-mix(in srgb, var(--brand-700) 8%, transparent);
}

:global(.login-forgot-dialog .el-dialog__title) {
  font-weight: 600;
  color: var(--text-primary);
}

/* =====================================================================
   登录 / 注册页 · 品牌深海鹦鹉螺主题
   - 布局由 template 内 Tailwind 类控制（栅格、宽度、间距、对齐）
   - 本块只负责视觉表现与微调；色值一律取自 design.md 既有令牌
     （--brand-* / --bg-* / --text-* / --border-* / --radius-* / --shadow-* 等）
   ===================================================================== */
</style>
