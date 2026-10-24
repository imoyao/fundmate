<template>
  <el-dialog
    :model-value="visible"
    title="家庭成员"
    width="560px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <p class="member-hint">
      账户可指定归属成员，用于按人汇总与筛选。邀请按<b>邮箱</b>建立：对方用同一邮箱首次登录后自动加入本家庭。
    </p>

    <el-table
      v-loading="loading"
      :data="members"
      size="small"
      class="member-table"
    >
      <el-table-column label="成员" min-width="150">
        <template #default="{ row }">
          <span class="member-name">{{ displayName(row) }}</span>
          <span v-if="row.id === currentUserId" class="member-tag">我</span>
          <span v-else-if="row.pending" class="member-tag">待加入</span>
        </template>
      </el-table-column>
      <el-table-column label="邮箱" min-width="170">
        <template #default="{ row }">
          <span class="member-email">{{ row.email || "—" }}</span>
        </template>
      </el-table-column>
      <el-table-column label="角色" width="118">
        <template #default="{ row }">
          <el-select
            v-if="isAdmin && row.id !== currentUserId"
            :model-value="row.role"
            size="small"
            @update:model-value="onRoleChange(row, $event)"
          >
            <el-option
              v-for="opt in FAMILY_ROLE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <span v-else>{{ row.role_label }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="isAdmin" label="操作" width="72">
        <template #default="{ row }">
          <el-button
            v-if="row.id !== currentUserId"
            link
            type="danger"
            size="small"
            @click="onRemove(row)"
            >移除</el-button
          >
        </template>
      </el-table-column>
    </el-table>

    <template v-if="isAdmin">
      <el-divider content-position="left">邀请成员</el-divider>
      <div class="invite-row">
        <el-input
          v-model="inviteEmail"
          placeholder="成员邮箱（与其登录邮箱一致）"
          clearable
        />
        <el-input
          v-model="inviteNickname"
          placeholder="昵称（可选）"
          clearable
        />
        <el-select v-model="inviteRole" class="invite-role">
          <el-option
            v-for="opt in FAMILY_ROLE_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-button type="primary" :loading="inviting" @click="onInvite"
          >邀请</el-button
        >
      </div>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getMe } from "@/api/auth";
import {
  FAMILY_ROLE_OPTIONS,
  inviteFamilyMember,
  listCurrentFamilyMembers,
  listFamilyMembers,
  removeFamilyMember,
  updateFamilyMember,
  type FamilyMember
} from "@/api/family";

/**
 * 家庭成员管理弹窗（#1173）。
 *
 * 为什么放在账户页而不是「个人中心」：成员存在的意义就是给账户分归属，
 * 「加了个成员但账户里选不到」是本次要消灭的断点——入口贴着账户列表，
 * 心智上是一条线（账户 → 谁的 → 谁）。
 *
 * 权限：主理人可邀请/改角色/移除；普通成员只读（`GET /api/users/` 可读，
 * 管理动作全部依赖后端 `require_roles('admin')`，前端置灰只是为了少一次 403）。
 */
const props = defineProps<{ visible: boolean }>();
const emit = defineEmits<{ "update:visible": [value: boolean] }>();

const loading = ref(false);
const inviting = ref(false);
const members = ref<FamilyMember[]>([]);
const familyId = ref<number | null>(null);
const currentUserId = ref<number | null>(null);
const currentRole = ref("member");

const inviteEmail = ref("");
const inviteNickname = ref("");
const inviteRole = ref("member");

const isAdmin = computed(() => currentRole.value === "admin");

/**
 * 单元格行对象：Element Plus 的 `#default="{ row }"` 槽位给的是 `DefaultRow`
 * （`Record<string, any>`），与 `FamilyMember` 互不兼容赋值，故这里只按结构读取。
 * 表格数据本身仍由 `members: FamilyMember[]` 保证形状。
 */
type MemberRow = Record<string, any>;

function displayName(m: MemberRow): string {
  return m.nickname || m.username || m.email || `成员 ${m.id}`;
}

function errorMessage(e: unknown, fallback: string): string {
  const err = e as { response?: { data?: { message?: string } } };
  return err?.response?.data?.message || fallback;
}

async function fetchMembers() {
  if (familyId.value === null) return;
  loading.value = true;
  try {
    // 主理人走管理接口（含 pending 标记）；其他角色走 /api/users/ 只读
    const res = isAdmin.value
      ? await listFamilyMembers(familyId.value)
      : await listCurrentFamilyMembers();
    members.value = (res as any)?.data ?? [];
  } catch (e) {
    ElMessage.error(errorMessage(e, "家庭成员加载失败"));
  } finally {
    loading.value = false;
  }
}

async function bootstrap() {
  loading.value = true;
  try {
    const res = await getMe();
    familyId.value = res?.data?.family?.id ?? null;
    currentUserId.value = res?.data?.id ?? null;
    currentRole.value = res?.data?.role || "member";
  } catch (e) {
    ElMessage.error(errorMessage(e, "获取当前家庭信息失败"));
  } finally {
    loading.value = false;
  }
  await fetchMembers();
}

watch(
  () => props.visible,
  val => {
    if (!val) return;
    inviteEmail.value = "";
    inviteNickname.value = "";
    inviteRole.value = "member";
    bootstrap();
  }
);

async function onInvite() {
  const email = inviteEmail.value.trim();
  if (!email) {
    ElMessage.warning("请填写成员邮箱");
    return;
  }
  if (familyId.value === null) return;
  inviting.value = true;
  try {
    await inviteFamilyMember(familyId.value, {
      email,
      nickname: inviteNickname.value.trim() || undefined,
      role: inviteRole.value
    });
    ElMessage.success("已创建邀请，对方用该邮箱首次登录后加入家庭");
    inviteEmail.value = "";
    inviteNickname.value = "";
    await fetchMembers();
  } catch (e) {
    ElMessage.error(errorMessage(e, "邀请失败"));
  } finally {
    inviting.value = false;
  }
}

async function onRoleChange(row: MemberRow, role: string) {
  if (familyId.value === null || role === row.role) return;
  try {
    await updateFamilyMember(familyId.value, row.id, { role });
    ElMessage.success("角色已更新");
    await fetchMembers();
  } catch (e) {
    ElMessage.error(errorMessage(e, "角色更新失败"));
    await fetchMembers();
  }
}

async function onRemove(row: MemberRow) {
  if (familyId.value === null) return;
  try {
    await ElMessageBox.confirm(
      `移除「${displayName(row)}」后，其名下账户仍留在本家庭，但归属会被清空。确定移除？`,
      "移除成员",
      { type: "warning", confirmButtonText: "移除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  try {
    await removeFamilyMember(familyId.value, row.id);
    ElMessage.success("已移除");
    await fetchMembers();
  } catch (e) {
    ElMessage.error(errorMessage(e, "移除失败"));
  }
}
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.member-hint {
  margin: 0 0 var(--space-4, 12px);
  font-size: var(--text-label, 13px);
  line-height: 20px;
  color: var(--text-tertiary-ink);
}

.member-name {
  color: var(--text-primary);
}

.member-tag {
  padding: 0 6px;
  margin-left: var(--space-2, 6px);
  font-size: var(--text-label, 13px);
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.member-email {
  font-size: var(--text-label, 13px);
  color: var(--text-secondary);
}

.invite-row {
  display: flex;
  gap: var(--space-3, 8px);
  align-items: center;
}

.invite-role {
  flex-shrink: 0;
  width: 110px;
}

@include bp.below("md") {
  .invite-row {
    flex-direction: column;
    align-items: stretch;
  }

  .invite-role {
    width: 100%;
  }
}
</style>
