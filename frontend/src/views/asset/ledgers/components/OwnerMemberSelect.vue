<template>
  <el-form-item label="归属成员">
    <el-select
      :model-value="modelValue"
      class="w-full"
      clearable
      :loading="loading"
      placeholder="不选择 = 家庭共有"
      @update:model-value="emit('update:modelValue', $event)"
    >
      <el-option
        v-for="m in options"
        :key="m.value"
        :label="m.label"
        :value="m.value"
      />
    </el-select>
    <div class="text-xs mt-1" :style="{ color: 'var(--text-tertiary-ink)' }">
      归属成员后可按人筛选资产与收益
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { listMemberProfiles } from "@/api/family";
import { memberOptions } from "@/views/asset/family/familyMemberModel";

/**
 * 账户归属家庭成员选择器（#1173）。
 *
 * WHY 组件自带数据加载（而不是父级传入候选列表）：
 * ① `AccountFormFields.vue` 有 vue 体积门禁的**只减不增**基线（587 行），
 *    归属成员若塞进那个共享组件会把它顶破；
 * ② 成员候选是「打开表单时拉一次」的低频数据，让组件自管更贴合使用场景，
 *    也免得三个宿主（建账 / 编辑 / 导入建账）各写一遍加载逻辑。
 *
 * 加载失败静默兜底为空候选——没有成员只是不能按人归属，账户照常能建。
 */
withDefaults(
  defineProps<{
    /** 当前选中的成员 ID（null = 未归属/家庭共有） */
    modelValue?: number | null;
  }>(),
  {
    modelValue: null
  }
);

const emit = defineEmits<{
  "update:modelValue": [value: number | null];
}>();

const options = ref<{ value: number; label: string }[]>([]);
const loading = ref(false);

const loadMembers = async () => {
  loading.value = true;
  try {
    const res = await listMemberProfiles();
    options.value = memberOptions(res.data);
  } catch {
    options.value = [];
  } finally {
    loading.value = false;
  }
};

onMounted(loadMembers);
</script>
