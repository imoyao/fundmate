/**
 * 家庭成员档案纯逻辑的回归网（#1173）。
 *
 * 判据纪律：断言完整行为，不只断言「函数存在」。
 * 重点是三处容易做错的口径：
 * 1. **停用成员不出现在归属下拉里**，但已绑账户仍要能显示原归属；
 * 2. **未归属是正常状态**（显示「家庭共有」，不是「未设置」——后者会让人以为漏配了）；
 * 3. **名下有账户的成员不能停用**（否则账户归属悬空）。
 */
import { describe, it, expect } from "vitest";
import {
  EMPTY_MEMBER_FORM,
  MEMBER_NAME_MAX,
  canDeactivate,
  deactivateEffectHint,
  memberOptions,
  ownerMemberText,
  validateMemberForm
} from "../familyMemberModel";
import type { FamilyMemberProfile } from "@/api/family";

const member = (
  over: Partial<FamilyMemberProfile> = {}
): FamilyMemberProfile => ({
  id: 1,
  name: "老婆",
  role: "spouse",
  role_label: "配偶",
  user_id: null,
  is_active: true,
  ledger_count: 0,
  ...over
});

describe("成员表单校验（#1173）", () => {
  it("空称谓被拒", () => {
    expect(validateMemberForm({ name: "", role: "other" })).toBe(
      "成员称谓不能为空"
    );
    expect(validateMemberForm({ name: "   ", role: "other" })).toBe(
      "成员称谓不能为空"
    );
  });

  it("超长称谓被拒（上限与后端模型列宽一致）", () => {
    const long = "a".repeat(MEMBER_NAME_MAX + 1);
    expect(validateMemberForm({ name: long, role: "other" })).toContain("过长");
  });

  it("合法称谓通过", () => {
    expect(validateMemberForm({ name: "老婆", role: "spouse" })).toBe("");
  });

  it("空表单初值的称谓为空（对话框打开即触发校验失败，符合预期）", () => {
    expect(EMPTY_MEMBER_FORM.name).toBe("");
    expect(validateMemberForm(EMPTY_MEMBER_FORM)).toBe("成员称谓不能为空");
  });

  it("新表单默认启用（停用是软删，可恢复）", () => {
    expect(EMPTY_MEMBER_FORM.is_active).toBe(true);
  });
});

describe("归属成员下拉候选项（#1173）", () => {
  it("只列启用成员——停用成员不该再被指派新账户", () => {
    const opts = memberOptions([
      member({ id: 1, name: "老婆" }),
      member({ id: 2, name: "已停用", is_active: false })
    ]);
    expect(opts).toEqual([{ value: 1, label: "老婆" }]);
  });

  it("空列表返回空数组（不是 undefined）", () => {
    expect(memberOptions([])).toEqual([]);
    expect(memberOptions(null)).toEqual([]);
    expect(memberOptions(undefined)).toEqual([]);
  });
});

describe("账户归属展示（#1173）", () => {
  it("未归属显示「家庭共有」——不是「未设置」", () => {
    // 「未设置」会让人以为漏配了；家庭共有本就是多数账户的常态
    expect(ownerMemberText({ owner_member_id: null })).toBe("家庭共有");
    expect(ownerMemberText(null)).toBe("家庭共有");
    expect(ownerMemberText(undefined)).toBe("家庭共有");
  });

  it("已归属显示成员称谓", () => {
    expect(
      ownerMemberText({ owner_member_id: 1, owner_member_name: "老婆" })
    ).toBe("老婆");
  });

  it("有 ID 但没有称谓时兜底为「未知成员」（不回落到「家庭共有」）", () => {
    // 兜底成「家庭共有」是错的：那会把「归属了但名字丢了」说成「没归属」
    expect(
      ownerMemberText({ owner_member_id: 1, owner_member_name: null })
    ).toBe("未知成员");
  });
});

describe("成员停用语义（#1173）", () => {
  it("启用中的成员可停用（哪怕名下有账户——停用是软删，归属保留）", () => {
    expect(canDeactivate(member({ ledger_count: 0 }))).toBe(true);
    expect(canDeactivate(member({ ledger_count: 2 }))).toBe(true);
  });

  it("已停用的成员不可再停用（幂等）", () => {
    expect(canDeactivate(member({ is_active: false }))).toBe(false);
  });

  it("影响说明写明账户归属保留（用户要知道停用不会丢归属）", () => {
    const hint = deactivateEffectHint(member({ ledger_count: 3 }));
    expect(hint).toContain("3");
    expect(hint).toContain("仍归属");
  });

  it("无账户时也给可恢复的提示", () => {
    expect(deactivateEffectHint(member({ ledger_count: 0 }))).toContain("恢复");
  });
});
