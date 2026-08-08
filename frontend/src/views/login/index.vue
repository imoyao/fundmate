<template>
  <div class="select-none">
    <img :src="bg" class="wave" />
    <div class="flex-c absolute right-5 top-3">
      <el-switch
        v-model="dataTheme"
        inline-prompt
        :active-icon="dayIcon"
        :inactive-icon="darkIcon"
        @change="dataThemeChange"
      />
    </div>
    <div class="login-container">
      <div class="img">
        <component :is="toRaw(illustration)" />
      </div>
      <div class="login-box">
        <div class="login-form">
          <avatar class="avatar" />
          <Motion>
            <h2 class="outline-hidden">
              {{ isRegisterMode ? "创建账户" : title }}
            </h2>
          </Motion>

          <el-form
            ref="ruleFormRef"
            :model="ruleForm"
            :rules="isRegisterMode ? registerRules : loginRules"
            size="large"
          >
            <!-- 邮箱 / 用户名（登录模式二选一） -->
            <Motion :delay="100">
              <el-form-item prop="email">
                <el-input
                  v-model="ruleForm.email"
                  clearable
                  :placeholder="isRegisterMode ? '邮箱地址' : '邮箱或用户名'"
                  :prefix-icon="useRenderIcon(User)"
                />
              </el-form-item>
            </Motion>

            <!-- 昵称（仅注册模式） -->
            <Motion v-if="isRegisterMode" :delay="150">
              <el-form-item prop="username">
                <el-input
                  v-model="ruleForm.username"
                  clearable
                  placeholder="昵称（用于展示）"
                  :prefix-icon="useRenderIcon(User)"
                />
              </el-form-item>
            </Motion>

            <!-- 密码 -->
            <Motion :delay="200">
              <el-form-item prop="password">
                <el-input
                  v-model="ruleForm.password"
                  clearable
                  show-password
                  placeholder="密码（至少8位）"
                  :prefix-icon="useRenderIcon(Lock)"
                />
              </el-form-item>
            </Motion>

            <!-- 确认密码（仅注册模式） -->
            <Motion v-if="isRegisterMode" :delay="250">
              <el-form-item prop="confirmPassword">
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
            <Motion v-if="isRegisterMode" :delay="300">
              <el-form-item prop="agreePolicy">
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

            <!-- 提交按钮 -->
            <Motion :delay="isRegisterMode ? 350 : 250">
              <el-button
                class="w-full mt-4!"
                size="default"
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

          <!-- 登录提示 -->
          <div v-if="!isRegisterMode" class="login-hint mt-3">
            <span class="text-xs" style="color: var(--text-tertiary)">
              💡 使用邮箱或用户名登录
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
  </div>
</template>

<script setup lang="ts">
import Motion from "./utils/motion";
import { useRouter } from "vue-router";
import { message } from "@/utils/message";
import { ref, reactive, toRaw, computed } from "vue";
import { debounce } from "@pureadmin/utils";
import { useNav } from "@/layout/hooks/useNav";
import { useEventListener } from "@vueuse/core";
import type { FormInstance, FormRules } from "element-plus";
import { useLayout } from "@/layout/hooks/useLayout";
import { initRouter } from "@/router/utils";
import { bg, avatar, illustration } from "./utils/static";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";

import dayIcon from "@/assets/svg/day.svg?component";
import darkIcon from "@/assets/svg/dark.svg?component";
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
const ruleFormRef = ref<FormInstance>();
const isRegisterMode = ref(false);
const showRegisterSuccess = ref(false);

const { initStorage } = useLayout();
initStorage();

const { dataTheme, overallStyle, dataThemeChange } = useDataThemeChange();
dataThemeChange(overallStyle.value);
const { title } = useNav();

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
    { min: 2, max: 20, message: "昵称长度 2-20 个字符", trigger: "blur" },
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
            emailRedirectTo: `${window.location.origin}/welcome`,
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

<style scoped>
@import url("@/style/login.css");
</style>

<style lang="scss" scoped>
/* 响应式 */
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

:deep(.el-input-group__append, .el-input-group__prepend) {
  padding: 0;
}

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

.login-hint {
  text-align: center;
}

.register-success {
  margin-top: 12px;
}
</style>
