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

/** 登录标识解析（D10）：把"邮箱 或 用户名"解析为规范邮箱，供二次登录 */
export type ResolveResult = {
  data: { email: string };
  message: string;
};

export const resolveIdentifier = (identifier: string) => {
  return http.request<ResolveResult>("post", "/api/auth/resolve", {
    data: { identifier }
  });
};

/** 个人中心资料更新（PATCH /api/users/me） */
export type ProfileUpdate = {
  username?: string;
  nickname?: string;
  avatar?: string;
};

export const updateMe = (payload: ProfileUpdate) => {
  return http.request<MeResult>("patch", "/api/users/me", { data: payload });
};
