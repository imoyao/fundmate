import { http } from "@/utils/http";

/** 当前登录用户信息（含角色与所属家庭），与后端 `GET /api/auth/me` 契约 */
export type MeResult = {
  data: {
    id: number;
    supabase_id: string | null;
    username: string | null;
    nickname: string | null;
    avatar: string | null;
    email: string | null;
    role: string;
    role_label: string;
    family: {
      id: number;
      name: string | null;
    };
  };
  message: string;
};

/** 获取当前登录用户信息 */
export const getMe = () => {
  return http.request<MeResult>("get", "/api/auth/me");
};

/** 退出登录：统一走后端接口，由后端服务端作废 Supabase 会话 */
export const logoutApi = (supabaseToken?: string | null) => {
  return http.request<{ success: boolean }>(
    "post",
    "/api/auth/logout",
    supabaseToken
      ? { headers: { Authorization: `Bearer ${supabaseToken}` } }
      : {}
  );
};
