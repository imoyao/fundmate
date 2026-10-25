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
};

/**
 * 家庭成员**档案**（#1173）：账本账户的归属维度。
 *
 * 与上面的 `FamilyMember`（登录账号 + 权限角色）**不是一回事**：
 * - 登录账号 = 能登录 App 的人，带 admin/member/viewer 权限角色；
 * - 成员档案 = 「这笔钱是谁的」，成员可能没有 App 账号（如「老婆」），
 *   角色是家庭内的身份（本人/配偶/子女/父母/其他）。
 */
export type FamilyMemberProfile = {
  id: number;
  name: string;
  role: string;
  role_label: string;
  user_id: number | null;
  is_active: boolean;
  /** 该成员名下绑定的账户数（删成员前要看这个数） */
  ledger_count: number;
  created_at?: string | null;
  updated_at?: string | null;
};

/** 家庭内角色词表（与后端 `MEMBER_ROLE_LABELS` 一致） */
export const MEMBER_ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: "self", label: "本人" },
  { value: "spouse", label: "配偶" },
  { value: "child", label: "子女" },
  { value: "parent", label: "父母" },
  { value: "other", label: "其他" }
];

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

// ── 成员档案 CRUD（#1173）───────────────────────────────────────────────────

/** 列出家庭成员档案（全角色可读：viewer 也要能看见账户归属是谁） */
export const listMemberProfiles = () => {
  return http.request<{ data: FamilyMemberProfile[]; message: string }>(
    "get",
    "/api/families/members/profiles/"
  );
};

/** 新增成员档案（仅主理人） */
export const createMemberProfile = (data: { name: string; role?: string }) => {
  return http.request<{ data: FamilyMemberProfile; message: string }>(
    "post",
    "/api/families/members/profiles/",
    { data }
  );
};

/** 改成员档案（仅主理人） */
export const updateMemberProfile = (
  id: number,
  data: { name?: string; role?: string; is_active?: boolean }
) => {
  return http.request<{ data: FamilyMemberProfile; message: string }>(
    "patch",
    `/api/families/members/profiles/${id}/`,
    { data }
  );
};

/** 停用成员档案（软删，仅主理人） */
export const deleteMemberProfile = (id: number) => {
  return http.request<{ data: FamilyMemberProfile; message: string }>(
    "delete",
    `/api/families/members/profiles/${id}/`
  );
};
