<template>
  <div
    class="family-member-page p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 页面标题 & 操作栏 -->
    <div
      class="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between"
    >
      <div>
        <h2
          class="text-2xl font-bold whitespace-nowrap"
          :style="{ color: 'var(--text-primary)' }"
        >
          家庭成员
        </h2>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary-ink)' }">
          把账户归属到具体成员，之后就能按人看资产、做汇总
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <el-button
          class="btn-ghost-text"
          @click="$router.push('/asset/ledgers')"
        >
          <IconifyIconOffline icon="ep:wallet" class="mr-1" /> 账户管理
        </el-button>
        <el-button type="primary" @click="openCreateDialog">
          <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新增成员
        </el-button>
      </div>
    </div>

    <!-- 加载态 -->
    <div
      v-if="loading"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      <el-icon class="is-loading"><Loading /></el-icon>
    </div>

    <!-- 空状态 -->
    <div
      v-else-if="!members.length"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      <p class="mb-2">还没有家庭成员</p>
      <p class="text-sm mb-4">
        成员是「这笔钱是谁的」的归属维度。添加成员后，就能把账户挂到具体成员名下
      </p>
      <el-button type="primary" @click="openCreateDialog">新增成员</el-button>
    </div>

    <!-- 成员列表 -->
    <el-table v-else :data="members" size="small" empty-text="暂无家庭成员">
      <el-table-column label="称谓" min-width="160">
        <template #default="{ row }">
          <div class="flex items-center gap-2">
            <span class="font-medium" :style="{ color: 'var(--text-primary)' }">
              {{ row.name }}
            </span>
            <el-tag v-if="!row.is_active" size="small" type="info">
              已停用
            </el-tag>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="身份" width="120">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row.role_label }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="名下账户" width="110" align="right">
        <template #default="{ row }">
          <span :style="{ color: 'var(--text-secondary)' }">
            {{ row.ledger_count }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="160" align="right">
        <template #default="{ row }">
          <el-button
            text
            size="small"
            @click="openEditDialog(row as MemberRow)"
          >
            编辑
          </el-button>
          <el-button
            text
            size="small"
            type="danger"
            :disabled="!canDeactivate(row as MemberRow)"
            :title="
              canDeactivate(row as MemberRow)
                ? deactivateEffectHint(row as MemberRow)
                : '该成员已停用'
            "
            @click="handleDeactivate(row as MemberRow)"
          >
            停用
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增 / 编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingMember ? '编辑成员' : '新增成员'"
      width="420px"
      append-to-body
    >
      <el-form label-width="72px" @submit.prevent>
        <el-form-item label="称谓">
          <el-input
            v-model="form.name"
            placeholder="如：老婆"
            maxlength="50"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="身份">
          <el-select v-model="form.role" class="w-full">
            <el-option
              v-for="opt in MEMBER_ROLE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <!-- 停用是软删：名下账户仍归属该成员，只是不能再被指派新账户（#1173） -->
        <el-form-item v-if="editingMember" label="启用状态">
          <el-switch
            v-model="form.is_active"
            active-text="启用"
            inactive-text="已停用"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { Loading } from "@element-plus/icons-vue";
import {
  MEMBER_ROLE_OPTIONS,
  createMemberProfile,
  deleteMemberProfile,
  listMemberProfiles,
  updateMemberProfile
} from "@/api/family";
import type { FamilyMemberProfile } from "@/api/family";
import {
  EMPTY_MEMBER_FORM,
  type MemberForm,
  canDeactivate,
  deactivateEffectHint,
  validateMemberForm
} from "./familyMemberModel";

defineOptions({ name: "AssetFamilyMembers" });

/** el-table 的 slot row 是 `DefaultRow`（元素无具体类型），这里收窄成成员档案类型 */
type MemberRow = FamilyMemberProfile;

const members = ref<FamilyMemberProfile[]>([]);
const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);
const editingMember = ref<FamilyMemberProfile | null>(null);
const form = ref<MemberForm>({ ...EMPTY_MEMBER_FORM });

const fetchMembers = async () => {
  loading.value = true;
  try {
    const res = await listMemberProfiles();
    members.value = res.data || [];
  } catch (e) {
    ElMessage.error("成员列表加载失败");
  } finally {
    loading.value = false;
  }
};

const openCreateDialog = () => {
  editingMember.value = null;
  form.value = { ...EMPTY_MEMBER_FORM };
  dialogVisible.value = true;
};

const openEditDialog = (member: FamilyMemberProfile) => {
  editingMember.value = member;
  form.value = {
    name: member.name,
    role: member.role,
    is_active: member.is_active
  };
  dialogVisible.value = true;
};

const handleSave = async () => {
  const err = validateMemberForm(form.value);
  if (err) {
    ElMessage.warning(err);
    return;
  }
  saving.value = true;
  try {
    if (editingMember.value) {
      await updateMemberProfile(editingMember.value.id, {
        name: form.value.name.trim(),
        role: form.value.role,
        is_active: form.value.is_active
      });
      ElMessage.success("成员已更新");
    } else {
      await createMemberProfile({
        name: form.value.name.trim(),
        role: form.value.role
      });
      ElMessage.success("成员已添加");
    }
    dialogVisible.value = false;
    await fetchMembers();
  } catch (e) {
    ElMessage.error("保存失败");
  } finally {
    saving.value = false;
  }
};

const handleDeactivate = async (member: FamilyMemberProfile) => {
  if (!canDeactivate(member)) {
    ElMessage.warning(deactivateBlockedReason(member));
    return;
  }
  try {
    await deleteMemberProfile(member.id);
    ElMessage.success("成员已停用");
    await fetchMembers();
  } catch (e) {
    ElMessage.error("停用失败");
  }
};

onMounted(fetchMembers);
</script>
