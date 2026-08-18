// frontend/src/utils/supabase.ts
import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

// 环境标识：区分 Server 端（development/staging）与 Product 端（production）。
// Vite 内置 import.meta.env.MODE / DEV / PROD 也可直接使用，此处显式暴露便于业务判断。
export const APP_ENV =
  (import.meta.env.VITE_APP_ENV as string | undefined) ??
  (import.meta.env.PROD ? "production" : "development");

if (import.meta.env.DEV && (!supabaseUrl || !supabaseAnonKey)) {
  console.warn(
    `[supabase] 当前环境(${APP_ENV})未配置 VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY，登录注册将不可用`
  );
}

/**
 * 跨子域 SSO 的 cookie 配置。
 *
 * 把 Supabase session 写到 `.duoduobei.com` 父域（而非默认的子域 localStorage），
 * 这样 jigu.duoduobei.com 与 app.duoduobei.com 共享同一份登录态，实现「任一站登录、
 * 另一站免登」。开发环境（localhost）无法写父域 cookie，回退到默认（当前域）即可，
 * 本地 SSO 不生效但功能正常。
 */
const isDev = import.meta.env.DEV;
const cookieDomain = import.meta.env.VITE_SUPABASE_COOKIE_DOMAIN as
  | string
  | undefined;

const authCookieOptions = isDev
  ? undefined
  : {
      domain: cookieDomain ?? ".duoduobei.com",
      path: "/",
      sameSite: "lax" as const,
      secure: true
    };

/**
 * Supabase 浏览器端客户端（支持跨子域 SSO）。
 * 使用 @supabase/ssr 的 createBrowserClient，通过 cookieOptions 将 session 持久化到父域 cookie。
 */
export const supabase: SupabaseClient = createBrowserClient(
  supabaseUrl,
  supabaseAnonKey,
  {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      ...(authCookieOptions ? { cookieOptions: authCookieOptions } : {})
    }
  }
);
