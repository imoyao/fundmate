/**
 * 家庭成员归属前端接线守卫（#1173）。
 *
 * WHY 用源码文本断言而不是挂载组件：vitest 的 `environment: "node"` 跑不了
 * 组件（挂载会拉起 router / supabase）。仓库既有做法见
 * `views/asset/ledgers/__tests__/allocationEditGuard.spec.ts`（同类范式）。
 *
 * 判据纪律：断言**完整调用子串（含传参）**，不是裸标识符——裸标识符出现
 * 只说明「某处提到了这个词」，说明不了「参数真的传下去了」。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const view = (rel: string) => read(`../../../${rel}`);

describe("账户归属成员接线（#1173）", () => {
  it("归属成员选择器独立成组件（不塞进共享的 AccountFormFields）", () => {
    // WHY 独立组件：`AccountFormFields.vue` 有 vue 体积门禁的**只减不增**基线，
    // 归属成员塞进去会把它顶破；且成员候选要「打开表单时拉一次」，由组件自管更贴合。
    const src = view("asset/ledgers/components/OwnerMemberSelect.vue");
    expect(src).toContain('label="归属成员"');
    // 组件自带候选加载，父级只传 v-model
    expect(src).toContain("listMemberProfiles");
    // 下拉必须能清空——「不选择 = 家庭共有」是默认状态，不能强制选一个
    expect(src).toContain("clearable");

    // 共享表单组件里不得再有归属成员（否则体积基线与单一口径都被破坏）
    const shared = view("asset/ledgers/components/AccountFormFields.vue");
    expect(shared).not.toContain("归属成员");
  });

  it("三个建账/改账宿主都接了归属成员选择器", () => {
    const create = view("asset/ledgers/components/CreateAccountDialog.vue");
    expect(create).toContain(
      '<OwnerMemberSelect v-model="createForm.owner_member_id" />'
    );
    const edit = view("asset/ledgers/components/EditAccountDialog.vue");
    expect(edit).toContain(
      '<OwnerMemberSelect v-model="editForm.owner_member_id" />'
    );
    // 导入向导里新建账户是第三个宿主——漏了它「导入时建的账户无法归属」
    const importCreate = view(
      "asset/investment/import/components/CreateLedgerDialog.vue"
    );
    expect(importCreate).toContain(
      '<OwnerMemberSelect v-model="newLedgerOwnerMemberId" />'
    );
  });

  it("创建账户时把归属成员下发给后端", () => {
    const src = view("asset/ledgers/components/CreateAccountDialog.vue");
    expect(src).toContain("owner_member_id: createForm.value.owner_member_id");
  });

  it("编辑账户时回填并下发归属成员", () => {
    const src = view("asset/ledgers/components/EditAccountDialog.vue");
    // 回填
    expect(src).toContain("owner_member_id: info.owner_member_id ?? null");
    // 下发（editForm 整体展开成 payload，故字段名出现在表单类型里即可）
    expect(src).toContain("owner_member_id: number | null");
  });

  it("导入向导建账时下发归属成员", () => {
    const src = view("asset/investment/import/composables/useImportWizard.ts");
    expect(src).toContain(
      "payload.owner_member_id = newLedgerOwnerMemberId.value"
    );
  });

  it("账户卡片展示归属成员徽章（仅在有归属时）", () => {
    const src = view("asset/ledgers/components/LedgerCard.vue");
    expect(src).toContain("ledger.owner_member_id");
    expect(src).toContain("ledger.owner_member_name");
  });
});

describe("成员管理入口（#1173）", () => {
  it("路由已注册 /asset/family", () => {
    const src = read("../../../../router/modules/asset.ts");
    expect(src).toContain('path: "/asset/family"');
    expect(src).toContain('name: "AssetFamilyMembers"');
  });

  it("成员管理页存在且能增删改", () => {
    const src = view("asset/family/index.vue");
    expect(src).toContain("listMemberProfiles");
    expect(src).toContain("createMemberProfile");
    expect(src).toContain("updateMemberProfile");
    expect(src).toContain("deleteMemberProfile");
  });

  it("成员 API 封装齐全（前端不能只有后端有端点）", () => {
    const src = read("../../../../api/family.ts");
    expect(src).toContain("listMemberProfiles");
    expect(src).toContain("createMemberProfile");
    expect(src).toContain("updateMemberProfile");
    expect(src).toContain("deleteMemberProfile");
  });
});

describe("成员筛选参数贯通（#1173）", () => {
  it("持仓列表参数类型带 member_id", () => {
    const src = read("../../../../api/types.d.ts");
    expect(src).toContain("member_id?: number");
  });

  it("汇总 API 带 member_id 查询参数", () => {
    const src = read("../../../../api/summary.ts");
    expect(src).toContain("member_id");
  });
});
