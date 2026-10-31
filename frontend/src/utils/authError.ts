/**
 * Supabase Auth（GoTrue）错误 → 用户可读的中文提示。
 *
 * ## 为什么需要这一层
 *
 * 登录页此前是 `message(err.message || "…")`：supabase-js 把 GoTrue 的英文
 * message 原样包进 Error，于是用户看到的是
 * `Invalid login credentials` / `Invalid API key` / `Email not confirmed`
 * 这类**既看不懂、也无法据此行动**的英文——它既不是后端信封里的中文
 * `{message}`，也不是数据库直连错误，而是 Auth API 的错误被透传。
 *
 * ## 判据顺序（按稳定性从高到低）
 *
 *   1. `error.code`：GoTrue 的错误码是稳定契约，措辞（message）会随版本变；
 *   2. `error.message` 关键字：少数错误不带 code（如网络层 `Failed to fetch`）；
 *   3. `error.status`：429 / 5xx / 401 的兜底归类；
 *   4. 自带中文的 message 直接透传（如调用方自己 `throw new Error("未找到该用户名…")`）；
 *   5. 都不命中 → 通用中文兜底，**原始错误仍 console.warn**，避免修文案把线索修没了。
 *
 * ## 后端信封（2026-10-31，#2764）
 *
 * 本模块吃的不只是 Supabase 的 `AuthError`，还包括**后端接口**经 axios 抛出的错误。
 * 后者 `message` 是英文的 `Request failed with status code 404`，真正给人看的中文在
 * `response.data.message`（统一信封 `{data, message, error_code}`）。故
 * {@link normalizeAuthError} 优先取信封里的 message——否则 `POST /api/auth/resolve`
 * 的 404（用户名不存在）会退化成「操作失败，请稍后再试」，用户拿不到任何有效信息。
 *
 * 边界：本模块只管「文案」，不判断是否该重试、是否该跳转。
 */

/** 认证错误的最小形状（supabase-js 的 AuthError 结构子集）。 */
export interface AuthErrorLike {
  code?: string;
  message?: string;
  status?: number;
  name?: string;
}

/** 未识别错误的兜底文案（界面可见）。 */
export const AUTH_ERROR_FALLBACK = "操作失败，请稍后再试";

/** 按 GoTrue `error.code` 映射（优先命中）。 */
const CODE_MESSAGES: Record<string, string> = {
  invalid_credentials: "账号或密码不正确",
  user_not_found: "账号不存在",
  email_not_confirmed: "邮箱还未验证，请先查收验证邮件",
  phone_not_confirmed: "手机号还未验证",
  user_already_exists: "该邮箱已注册，请直接登录",
  email_exists: "该邮箱已注册，请直接登录",
  email_address_invalid: "邮箱地址格式不正确",
  email_address_not_authorized: "该邮箱不在允许注册的范围内",
  weak_password: "密码强度不足，请至少使用 8 位字符",
  same_password: "新密码不能与当前密码相同",
  signup_disabled: "暂未开放注册",
  email_provider_disabled: "暂不支持邮箱注册",
  provider_disabled: "该登录方式暂未开放",
  validation_failed: "提交的信息格式不正确，请检查后重试",
  over_request_rate_limit: "操作太频繁，请稍后再试",
  over_email_send_rate_limit: "邮件发送太频繁，请稍后再试",
  over_sms_send_rate_limit: "短信发送太频繁，请稍后再试",
  otp_expired: "链接或验证码已失效，请重新获取",
  bad_jwt: "登录状态已失效，请重新登录",
  refresh_token_not_found: "登录状态已失效，请重新登录",
  session_not_found: "登录状态已失效，请重新登录",
  session_expired: "登录状态已失效，请重新登录",
  reauthentication_needed: "为了安全，请重新登录后再操作",
  captcha_failed: "人机校验未通过，请重试",
  mfa_verification_failed: "验证码不正确",
  mfa_challenge_expired: "验证已超时，请重新获取验证码",
  insufficient_aal: "请先完成二次验证",
  hook_timeout: "服务响应超时，请稍后再试",
  unexpected_failure: "服务暂时不可用，请稍后再试"
};

/** 按 `error.message` 关键字兜底（GoTrue 少数错误不带 code）。 */
const MESSAGE_RULES: Array<[RegExp, string]> = [
  [
    /invalid api key|no api key found|secret api key required/i,
    "服务认证配置异常，请联系管理员"
  ],
  [/invalid login credentials/i, "账号或密码不正确"],
  [/email not confirmed/i, "邮箱还未验证，请先查收验证邮件"],
  [
    /user already registered|already been registered/i,
    "该邮箱已注册，请直接登录"
  ],
  [/password should be at least/i, "密码强度不足，请至少使用 8 位字符"],
  [/for security purposes|only request this after/i, "操作太频繁，请稍后再试"],
  [/email address .*invalid|invalid .*email/i, "邮箱地址格式不正确"],
  [/jwt expired|token .*expired/i, "登录状态已失效，请重新登录"],
  [
    /failed to fetch|networkerror|network request failed|load failed/i,
    "网络异常，请检查网络后重试"
  ],
  [/timeout|timed out/i, "服务响应超时，请稍后再试"]
];

const CJK_RE = /[\u4e00-\u9fff]/;

/** 把任意抛出物收敛成 AuthErrorLike（字符串、Error、普通对象都能吃）。 */
export function normalizeAuthError(err: unknown): AuthErrorLike {
  if (!err) return {};
  if (typeof err === "string") return { message: err };
  if (typeof err === "object") {
    const e = err as AuthErrorLike & {
      error_description?: string;
      response?: { status?: number; data?: { message?: string } };
    };
    // 后端（axios 拦截器）抛的是 AxiosError：`message` 是英文的
    // 「Request failed with status code 404」，真正给人看的中文在
    // `response.data.message`（本仓统一信封 {data, message, error_code}）。
    // 不读这一层的话，resolve 的 404 会一路掉到「操作失败，请稍后再试」——
    // 用户输错用户名时得不到任何有效信息（#2764）。
    const backendMessage =
      typeof e.response?.data?.message === "string"
        ? e.response.data.message
        : "";
    return {
      code: typeof e.code === "string" ? e.code : undefined,
      message: backendMessage || e.message || e.error_description || undefined,
      status: typeof e.status === "number" ? e.status : e.response?.status,
      name: typeof e.name === "string" ? e.name : undefined
    };
  }
  return {};
}

/**
 * 取用户可见的中文提示。
 *
 * 未识别时返回 {@link AUTH_ERROR_FALLBACK}，并把原始错误打到控制台（便于排查，
 * 又不会让英文/堆栈出现在界面上）。
 */
export function toAuthErrorMessage(err: unknown): string {
  const { code, message, status } = normalizeAuthError(err);

  if (code && CODE_MESSAGES[code]) return CODE_MESSAGES[code];

  const raw = (message || "").trim();
  for (const [re, text] of MESSAGE_RULES) {
    if (re.test(raw)) return text;
  }

  // 调用方自己抛的中文错误（如「未找到该用户名对应的账户」）：原样透传
  if (raw && CJK_RE.test(raw)) return raw;

  if (status === 429) return "操作太频繁，请稍后再试";
  if (status === 401) return "登录状态已失效，请重新登录";
  if (typeof status === "number" && status >= 500) {
    return "服务暂时不可用，请稍后再试";
  }

  console.warn("[auth] 未识别的认证错误：", code, raw, err);
  return AUTH_ERROR_FALLBACK;
}
