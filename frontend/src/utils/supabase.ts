// frontend/src/utils/supabase.ts
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

// 环境标识：区分 Server 端（development/staging）与 Product 端（production）。
// Vite 内置 import.meta.env.MODE / DEV / PROD 也可直接使用，此处显式暴露便于业务判断。
export const APP_ENV =
  (import.meta.env.VITE_APP_ENV as string | undefined) ??
  (import.meta.env.PROD ? "production" : "development");

if (import.meta.env.DEV && (!supabaseUrl || !supabaseAnonKey)) {
  console.warn(
    `[supabase] 当前环境(${APP_ENV})未配置 VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY，登录注册将不可用`,
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
