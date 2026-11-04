import { useRouter } from "vue-router";
import { message } from "@/utils/message";
import { nextTick, ref, reactive, computed } from "vue";
import { debounce } from "@pureadmin/utils";
import { useEventListener } from "@vueuse/core";
import type { FormInstance, FormRules } from "element-plus";
import { initRouter } from "@/router/utils";
import { supabase } from "@/utils/supabase";
import { ensureLocalProfile, resolveIdentifier } from "@/api/auth";
import { toAuthErrorMessage } from "@/utils/authError";
import { textLength } from "@/utils/textLength";
import { buildAppUrl, DOCS_SITE_URL } from "@/utils/appUrl";

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
      { required: true, message: "请输入用户名", trigger: "blur" },
      {
        // 码点口径（与后端 len() 一致，D73）：async-validator 的 min/max
        // 按 UTF-16 .length 计，emoji 下与后端不一致，故手写校验
        validator: (_rule, value: string, callback) => {
          const len = textLength(value);
          if (len < 5 || len > 20) {
            callback(new Error("用户名长度 5-20 个字符"));
            return;
          }
          callback();
        },
        trigger: "blur"
      },
      {
        pattern: /^[\u4e00-\u9fa5a-zA-Z0-9_]+$/,
        message: "用户名只能包含中文、字母、数字和下划线",
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
  // 隐私政策 / 用户协议在**文档站**（docs.duoduobei.com），应用站没有这两条路由：
  // 此前 window.open("/privacy") 打开的是应用站根路径，hash 为空 ⇒ 落到 /welcome。
  const openPrivacyPolicy = () => {
    window.open(`${DOCS_SITE_URL}/privacy`, "_blank");
  };

  const openTerms = () => {
    window.open(`${DOCS_SITE_URL}/terms`, "_blank");
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
          redirectTo: buildAppUrl("/")
        }
      });
      if (error) throw error;
      // 成功时 Supabase 会重定向到 GitHub，无需手动处理
    } catch (err: any) {
      message(toAuthErrorMessage(err), { type: "error" });
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
            redirectTo: buildAppUrl("/reset-password")
          }
        );
        if (error) throw error;
        // 防用户枚举：不区分邮箱是否存在，统一提示已发送
        message("重置邮件已发送，请查收邮箱", { type: "success" });
        forgotVisible.value = false;
      } catch (err: any) {
        message(toAuthErrorMessage(err), { type: "error" });
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
          const { data, error } = await supabase.auth.signUp({
            email: ruleForm.email.trim(),
            password: ruleForm.password,
            options: {
              // 邮箱验证回调回根路径，由前端守卫接管跳转；hash 模式由 buildAppUrl 拼 `#/`
              emailRedirectTo: buildAppUrl("/"),
              data: {
                username: ruleForm.username.trim()
              }
            }
          });

          if (error) throw error;

          // 注册即建号（#2764 遗留项）：项目关闭邮箱验证时 signUp 直接返回 session，
          // 此刻立即让后端建出本地映射行；否则用户随后用「用户名」登录，
          // 匿名 resolve 查不到行 → 404（登录页只能提示「未找到」）。
          // 开启邮箱验证时没有 session，建号发生在「点邮件回跳后的首个带 token 请求」。
          if (data.session) {
            const desired = ruleForm.username.trim();
            const profile = await ensureLocalProfile();
            // 后端遇到同名会加后缀（`_2`）而不是报错——不告诉用户，他会以为名字没生效
            if (
              profile?.username &&
              desired &&
              profile.username.toLowerCase() !== desired.toLowerCase()
            ) {
              message(
                `用户名「${desired}」已被占用，已为你分配「${profile.username}」`,
                {
                  type: "warning"
                }
              );
            }
          }

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

          // 幂等建号（#2764 遗留项）：老账号在本地可能还没映射行（注册时未走过带
          // token 的请求）。失败不阻断登录——下一次带 token 的请求会自动补建。
          await ensureLocalProfile();

          message("登录成功", { type: "success" });
          await initRouter();
          router.push("/welcome");
        }
      } catch (err: any) {
        message(toAuthErrorMessage(err), { type: "error" });
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
