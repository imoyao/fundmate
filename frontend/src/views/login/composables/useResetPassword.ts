import { ref, reactive, computed, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import type { FormInstance, FormRules } from "element-plus";
import { message } from "@/utils/message";
import { supabase } from "@/utils/supabase";
import { toAuthErrorMessage } from "@/utils/authError";

/** 重置密码页状态机：checking（等待链接验证）→ ready（可改密）/ expired（链接无效） */
export type ResetPasswordState = "checking" | "ready" | "expired";

/**
 * 重置密码页的表单状态与提交逻辑（#980 同源拆分）。
 *
 * 抽成 composable 的两个原因：
 *   1. 页面文件已贴着 `check_vue_size` 的「只减不增」基线，任何新增行（哪怕一行 import）
 *      都会判红——把逻辑搬出来才算净减少，而不是靠删空行对冲；
 *   2. 状态机（链接验证 → 可改密 / 过期）与表单校验是纯逻辑，跟模板无关，本就该独立测。
 */
export function useResetPassword() {
  const router = useRouter();
  const state = ref<ResetPasswordState>("checking");
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
      } catch (err) {
        // 用户可见文案统一走中文映射，原始英文/错误码只进控制台
        message(toAuthErrorMessage(err), { type: "error" });
      } finally {
        loading.value = false;
      }
    });
  };

  return { state, loading, formRef, form, rules, onSubmit };
}
