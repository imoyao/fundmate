import { http } from "@/utils/http";

/** 当前登录用户信息（含角色与所属家庭），与后端 `GET /api/auth/me/` 契约 */
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
  return http.request<MeResult>("get", "/api/auth/me/");
};

/**
 * 幂等建号触发器（#2764 遗留项）：登录 / 注册成功后调一次，让后端把本地 `users`
 * 映射行建出来。
 *
 * 为什么必须显式调：`users` 行由「首次带 token 的受保护请求」JIT 创建，而用户名登录
 * 的第一步 `POST /api/auth/resolve` 是**匿名**的——新用户若从未触发过带 token 的请求，
 * 用用户名登录必然 404。路由守卫里那次 `getMe` 带 `!userInfo` 条件（本地有旧会话资料
 * 就不拉），靠不住。
 *
 * 失败**不抛**：登录/注册本身已成功，建号会在下一次带 token 的请求里自动重试。
 */
export const ensureLocalProfile = async (): Promise<
  MeResult["data"] | null
> => {
  try {
    const res = await getMe();
    return res.data;
  } catch (e) {
    console.warn("初始化本地用户资料失败（下次带 token 请求会自动重试）：", e);
    return null;
  }
};

/** 退出登录：统一走后端接口，由后端服务端作废 Supabase 会话 */
export const logout = (supabaseToken?: string | null) => {
  return http.request<{ success: boolean }>(
    "post",
    "/api/auth/logout/",
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
  return http.request<ResolveResult>("post", "/api/auth/resolve/", {
    data: { identifier }
  });
};

/** 个人中心资料更新（PATCH /api/users/me/） */
export type ProfileUpdate = {
  username?: string;
  nickname?: string;
  avatar?: string;
};

export const updateMe = (payload: ProfileUpdate) => {
  return http.request<MeResult>("patch", "/api/users/me/", { data: payload });
};
