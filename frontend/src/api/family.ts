import { http } from "@/utils/http";

/** 家庭成员项，与后端 `GET /api/families/<id>/members/` 契约 */
export type FamilyMember = {
  id: number;
  username: string | null;
  nickname: string | null;
  avatar: string | null;
  email: string | null;
  role: string;
  role_label: string;
  is_active: number;
  /** 已邀请、尚未用该邮箱登录过（本地映射行已建，Supabase 身份未绑定，#1173） */
  pending?: boolean;
};

/** 家庭成员角色选项（与后端 users/models.py 的 ROLE_LABELS 对齐） */
export const FAMILY_ROLE_OPTIONS = [
  { value: "admin", label: "主理人" },
  { value: "member", label: "成员" },
  { value: "viewer", label: "只读" }
] as const;

export type FamilyResult = {
  data: {
    id: number;
    name: string;
    created_at?: string;
    updated_at?: string;
  };
  message: string;
};

/** 创建家庭，当前用户自动成为主理人 */
export const createFamily = (data: { name: string }) => {
  return http.request<FamilyResult>("post", "/api/families/", { data });
};

/** 查看家庭成员（仅主理人） */
export const listFamilyMembers = (familyId: number) => {
  return http.request<{ data: FamilyMember[]; message: string }>(
    "get",
    `/api/families/${familyId}/members/`
  );
};

/**
 * 当前家庭的成员列表（`GET /api/users/`，任意角色可读）。
 *
 * 与 `listFamilyMembers` 的区别只在权限：后者限主理人（可看到「待加入」等管理信息），
 * 前者给「账户归属成员」下拉用——普通成员也要能选，否则归属功能对他们不可用。
 */
export const listCurrentFamilyMembers = () => {
  return http.request<{ data: FamilyMember[]; message: string }>(
    "get",
    "/api/users/"
  );
};

/** 邀请成员（仅主理人）：按邮箱预建，对方首次用该邮箱登录后加入家庭 */
export const inviteFamilyMember = (
  familyId: number,
  data: { email: string; nickname?: string; role?: string }
) => {
  return http.request<{ data: FamilyMember; message: string }>(
    "post",
    `/api/families/${familyId}/members/`,
    { data }
  );
};

/** 修改成员角色 / 昵称（仅主理人） */
export const updateFamilyMember = (
  familyId: number,
  userId: number,
  data: { role?: string; nickname?: string }
) => {
  return http.request<{ data: FamilyMember; message: string }>(
    "patch",
    `/api/families/${familyId}/members/${userId}/`,
    { data }
  );
};

/** 移除成员（仅主理人）：删本地映射，其名下账户归属置空 */
export const removeFamilyMember = (familyId: number, userId: number) => {
  return http.request("delete", `/api/families/${familyId}/members/${userId}/`);
};
