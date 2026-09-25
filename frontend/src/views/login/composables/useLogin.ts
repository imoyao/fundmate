import { useRouter } from "vue-router";
import { message } from "@/utils/message";
import { nextTick, ref, reactive, computed } from "vue";
import { debounce } from "@pureadmin/utils";
import { useEventListener } from "@vueuse/core";
import type { FormInstance, FormRules } from "element-plus";
import { initRouter } from "@/router/utils";
import { supabase } from "@/utils/supabase";
import { resolveIdentifier } from "@/api/auth";

/**
 * 登录 / 注册页状态单体（#980 P1-C 结构拆分）：
 * 表单状态 / 校验规则 / 登录注册提交 / GitHub OAuth / 忘记密码四段收敛在这里，
 * index.vue 只做编排，子组件经 page prop 注入同一实例（P1-A/B 同款模式）。
 * 子组件把 ruleFormRef / forgotFormRef 绑定到本文件导出的同名 Ref 上
 * （模板字符串 ref 命中 setup 同名绑定即写入 .value），此处直接读取、无需回写同步。
 */
export function useLogin() {
  const router = useRouter();
  const loading = ref(false);
  const disabled = ref(false);
  const githubLoading = ref(false);
  const ruleFormRef = ref<FormInstance>();
  const isRegisterMode = ref(false);
  const showRegisterSuccess = ref(false);

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
    // 切换模式只清值不够：email/password 两个 prop 的 el-form-item DOM 在两种模式下复用，
    // 若此前校验失败过，is-error 类与红字提示会残留并继续显示（:rules 切换不会自动清状态）。
    // 必须在 DOM 更新后清一次校验状态，保证任意次来回切换都不飘红。
    nextTick(() => ruleFormRef.value?.clearValidate());
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
          // 🔥 注册（原 .vue 内解构出的 data 从未使用，迁入 .ts 后触 lint，直接不取）
          const { error } = await supabase.auth.signUp({
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
            // 与 toggleMode 同理：切回登录后清一次校验状态，
            // 防止注册阶段残留的 error/success 视觉带到登录表单
            nextTick(() => ruleFormRef.value?.clearValidate());
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
          const { error } = await supabase.auth.signInWithPassword({
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

  return {
    loading,
    disabled,
    githubLoading,
    ruleFormRef,
    isRegisterMode,
    showRegisterSuccess,
    ruleForm,
    loginRules,
    registerRules,
    toggleMode,
    openPrivacyPolicy,
    openTerms,
    onGithubLogin,
    forgotVisible,
    forgotLoading,
    forgotFormRef,
    forgotForm,
    forgotRules,
    openForgotDialog,
    onForgotSubmit,
    onSubmit
  };
}
