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
