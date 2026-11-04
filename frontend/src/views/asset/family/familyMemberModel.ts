/**
 * 家庭成员档案的纯逻辑（#1173）。
 *
 * WHY 独立成模块：vitest 的 `environment: "node"` 跑不了组件（挂载会拉起
 * router / supabase），仓库既有做法是把可测逻辑抽成 `*Model.ts` 再单测
 * （先例：`views/asset/ledgers/components/ledgerCard/ledgerCardModel.ts`）。
 *
 * 这里承载的是「不依赖组件」的判断：表单校验、称谓回显、停用成员的可见性。
 */

import type { FamilyMemberProfile } from "@/api/family";

/** 空表单的初值（新增成员对话框用） */
export interface MemberForm {
  name: string;
  role: string;
  /** 启用状态：停用是软删，「编辑」里可恢复启用（#1173） */
  is_active: boolean;
}

export const EMPTY_MEMBER_FORM: MemberForm = {
  name: "",
  role: "other",
  is_active: true
};

/** 称谓长度上限（与后端模型列宽一致） */
export const MEMBER_NAME_MAX = 50;

/**
 * 校验成员表单，返回错误文案（空串 = 通过）。
 *
 * 与后端 `FamilyMemberCreate` 的校验**逐条对齐**：前端拦一道是为了即时反馈，
 * 后端那道才是权威（前端校验可被绕过）。
 */
export function validateMemberForm(form: MemberForm): string {
  const name = (form.name || "").trim();
  if (!name) {
    return "成员称谓不能为空";
  }
  if (name.length > MEMBER_NAME_MAX) {
    return `成员称谓过长（最多 ${MEMBER_NAME_MAX} 字）`;
  }
  return "";
}

/**
 * 账户归属下拉的可选项（#1173）。
 *
 * 只列**启用**成员：已停用的成员不该再被指派新账户——但已绑账户仍要能显示原归属
 * （后端保留历史归属，前端靠 `ledger.owner_member_name` 回显，不靠下拉）。
 */
export function memberOptions(
  members: FamilyMemberProfile[] | null | undefined
): { value: number; label: string }[] {
  if (!members || !members.length) {
    return [];
  }
  return members
    .filter(m => m.is_active)
    .map(m => ({ value: m.id, label: m.name }));
}

/**
 * 账户归属的展示文案（#1173）。
 *
 * `null` → 「家庭共有」而不是空字符串或「-」：账户没归属成员是**正常状态**
 * （多数账户本就是家庭共有），显示成「未设置」会让人以为漏配了。
 */
export function ownerMemberText(
  ledger:
    | { owner_member_id?: number | null; owner_member_name?: string | null }
    | null
    | undefined
): string {
  if (!ledger || !ledger.owner_member_id) {
    return "家庭共有";
  }
  return ledger.owner_member_name || "未知成员";
}

/**
 * 成员是否可以被停用（#1173）。
 *
 * 只有**已停用**的成员不再可停用（幂等）。
 *
 * 名下有账户**不阻止停用**——停用是软删（`is_active = False`）：账户归属保留、
 * 历史可追溯，只是不再允许把新账户或改绑指向该成员。这与后端
 * `services/family_member_service.deactivate_member` 的语义一致；
 * 真正会让归属悬空的是**硬删**，那条路已被后端堵死（改为软删）。
 */
export function canDeactivate(member: FamilyMemberProfile): boolean {
  return member.is_active;
}

/**
 * 停用后的影响说明（#1173）。
 *
 * 告诉用户「停用会发生什么」，而不是干巴巴一个「失败」——停用是可逆的
 * （编辑里能把 `is_active` 改回 true），用户需要知道账户归属不会丢。
 */
export function deactivateEffectHint(member: FamilyMemberProfile): string {
  return member.ledger_count > 0
    ? `停用后，该成员名下的 ${member.ledger_count} 个账户仍归属该成员（历史可追溯），但不能再新建或改绑账户到该成员`
    : "停用后不能再新建或改绑账户到该成员（随时可在「编辑」里恢复启用）";
}
