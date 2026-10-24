<template>
  <el-form-item label="归属成员">
    <el-select
      :model-value="modelValue"
      class="w-full"
      clearable
      :loading="loading"
      placeholder="不指定（家庭共享）"
      @update:model-value="emit('update:modelValue', $event ?? null)"
    >
      <el-option
        v-for="m in members"
        :key="m.id"
        :label="memberLabel(m)"
        :value="m.id"
      />
    </el-select>
    <p class="owner-hint">
      用于按人汇总/筛选；不指定时该账户属于家庭共享池，不计入任何成员
    </p>
  </el-form-item>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { listCurrentFamilyMembers, type FamilyMember } from "@/api/family";

/**
 * 账户「归属成员」下拉（#1173）。
 *
 * 自己拉数据而不是由父组件透传：`AccountFormFields` 有四个宿主（新建/编辑/资产录入/
 * 导入向导），把成员列表塞进那条 props 链会让每个宿主都为它加一次请求与一次转发。
 * 走 `GET /api/users/`（任意角色可读）而非主理人专用接口——普通成员编辑自己的账户
 * 时也要能选。
 */
defineProps<{ modelValue: number | null }>();

const emit = defineEmits<{ "update:modelValue": [value: number | null] }>();

const members = ref<FamilyMember[]>([]);
const loading = ref(false);

function memberLabel(m: FamilyMember): string {
  const name = m.nickname || m.username || m.email || `成员 ${m.id}`;
  // 「待加入」是管理信息，这里只按角色标注，避免下拉里出现过多状态噪声
  return m.role_label ? `${name}（${m.role_label}）` : name;
}

onMounted(async () => {
  loading.value = true;
  try {
    const res = await listCurrentFamilyMembers();
    members.value = (res as any)?.data ?? [];
  } catch {
    // 拿不到成员列表时降级为「只有未指定」——归属是可选字段，不该挡住建账
    members.value = [];
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.owner-hint {
  margin: var(--space-3, 8px) 0 0;
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-tertiary-ink);
}
</style>
