import type { BrowserContext } from "@playwright/test";

/**
 * 免登录注入：把一份**已登录的 Supabase 会话**以 cookie 形式塞进浏览器上下文（#1568）。
 *
 * 为什么不用真实登录：真实登录要走 Supabase Auth（外部依赖 + 真实账号 + 网络），
 * 会让「路由渲染」这类纯前端断言变成「外部服务可用性测试」，脆弱且慢。而
 * `@supabase/ssr` 的浏览器客户端把会话存在 cookie 里，`supabase.auth.getSession()`
 * 直接读它——所以只要 cookie 名与值格式对，守卫就会认为「已登录」。
 *
 * 格式（对 @supabase/ssr 0.5+ / supabase-js 2.x 实测，非猜测）：
 * - cookie 名：`sb-<project-ref>-auth-token`（project-ref = URL 主机名第一段）；
 * - cookie 值：`base64-` + base64url(会话 JSON)——见 @supabase/ssr 的
 *   `BASE64_PREFIX` 与 `stringFromBase64URL`；
 * - 单块写入即可：值 URI 编码后 < 3180 字符时用 base 名（不需要 `.0/.1` 分块）。
 *
 * 会话里的 `expires_at` 必须取未来时间：否则 supabase-js 会尝试 refresh（打网络），
 * 断言就会变成对外部服务的依赖。
 */

/** 与 playwright.config.ts 的 webServer.env 保持一致：E2E 用的假项目 */
const DEFAULT_SUPABASE_URL =
  process.env.VITE_SUPABASE_URL ?? "https://e2etest.supabase.co";

function projectRefOf(supabaseUrl: string): string {
  try {
    return new URL(supabaseUrl).hostname.split(".")[0];
  } catch {
    // 非法 URL 时退回一个确定值，避免用例因配置笔误抛在注入阶段（真错会体现在断言上）
    return "e2etest";
  }
}

export const E2E_SESSION_STORAGE_KEY = `sb-${projectRefOf(DEFAULT_SUPABASE_URL)}-auth-token`;

/** 构造一份「结构完整、时间未过期」的会话 JSON（不需要真实签名，前端不验签） */
export function buildSession(nowSec: number = Math.floor(Date.now() / 1000)) {
  return {
    access_token: "e2e-injected-access-token",
    token_type: "bearer",
    expires_in: 3600,
    expires_at: nowSec + 3600,
    refresh_token: "e2e-injected-refresh-token",
    user: {
      id: "00000000-0000-4000-8000-000000000000",
      aud: "authenticated",
      role: "authenticated",
      email: "e2e@example.com",
      email_confirmed_at: new Date(nowSec * 1000).toISOString(),
      created_at: new Date(nowSec * 1000).toISOString(),
      // roles 走 user_metadata：路由守卫的权限判断读的就是这里（默认 ["user"]，本仓无 meta.roles 约束）
      user_metadata: { roles: ["user"], username: "e2e", nickname: "E2E 用户" },
      app_metadata: { provider: "email", providers: ["email"] }
    }
  };
}

/** 把会话写进 cookie（必须在 page.goto 之前调用，会话才在首屏就生效） */
export async function injectSupabaseSession(
  context: BrowserContext,
  baseURL: string,
  storageKey: string = E2E_SESSION_STORAGE_KEY
): Promise<void> {
  const value = `base64-${Buffer.from(JSON.stringify(buildSession()), "utf8").toString("base64url")}`;
  await context.addCookies([{ name: storageKey, value, url: baseURL }]);
}
