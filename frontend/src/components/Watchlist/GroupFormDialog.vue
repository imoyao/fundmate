<!--
  GroupFormDialog · 分组新建/编辑轻量弹窗（强制复用，见 docs/design/components.md）
  - 与 TagFormDialog 同构：名称输入 + 莫兰迪色板点选 + 受控随机取色。
  - 列表展示交给 GroupManagerDialog（GitHub Labels 风格），二者彻底解耦。
  - props：modelValue(显隐)、group(传入则编辑、null 为新建)、usedColors(已用色，用于随机取色避开)。
  - emits：update:modelValue、saved(保存成功)。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="isEdit ? '编辑分组' : '新建分组'"
    width="440px"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
  >
    <div class="group-form">
      <label class="group-form__label">名称</label>
      <!-- 名称上限 20：分组名用于分组 Tab 展示（8em≈8 汉字截断），50 字远超实际用途；
           后端 max_length=50 兼容（前端先截断，避免「输到一半被静默截断」）。 -->
      <el-input
        v-model="form.name"
        placeholder="请输入分组名称（最多 20 个字符）"
        size="large"
        maxlength="20"
        show-word-limit
        :disabled="loading"
      />

      <label class="group-form__label">颜色</label>
      <div class="group-form__colors">
        <button
          v-for="c in PRESET_TAG_COLORS"
          :key="c"
          type="button"
          class="color-dot"
          :class="{
            'color-dot--active': form.color.toLowerCase() === c.toLowerCase()
          }"
          :style="{ backgroundColor: c }"
          :title="c"
          @click="form.color = c"
        />
        <button
          type="button"
          class="color-dot color-dot--random"
          title="设置随机颜色"
          @click="pickRandomColor"
        >
          <el-icon><Refresh /></el-icon>
        </button>
      </div>

      <div class="group-form__preview">
        <span class="group-pill" :style="pillStyle">{{
          form.name || "分组预览"
        }}</span>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleVisibleChange(false)">取消</el-button>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!form.name.trim()"
        @click="save"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import type { WatchlistGroup } from "@/api/watchlist";
import { createWatchlistGroup, updateWatchlistGroup } from "@/api/watchlist";
import {
  PRESET_TAG_COLORS,
  DEFAULT_TAG_COLOR,
  randomMorandiColor
} from "@/constants/watchlist";

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    /** 传入则编辑该分组，null/undefined 为新建 */
    group?: WatchlistGroup | null;
    /** 已占用颜色（用于随机取色时尽量避开） */
    usedColors?: string[];
    /** 已有分组名称列表，用于前端拦截重名（编辑时自动排除自身） */
    existingNames?: string[];
  }>(),
  { group: null, usedColors: () => [], existingNames: () => [] }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
  /** 仅新建成功时抛出，携带新分组，便于调用方自动选中（区别于编辑场景） */
  (e: "created", group: WatchlistGroup): void;
}>();

const loading = ref(false);
const form = reactive<{ name: string; color: string }>({
  name: "",
  color: DEFAULT_TAG_COLOR
});
const isEdit = computed(() => !!props.group?.id);

watch(
  () => props.modelValue,
  visible => {
    if (visible) {
      form.name = props.group?.name || "";
      form.color = props.group?.color || DEFAULT_TAG_COLOR;
    }
  },
  { immediate: true }
);

function handleVisibleChange(value: boolean) {
  emit("update:modelValue", value);
}

const pillStyle = computed(() => ({
  backgroundColor: `${form.color}22`,
  color: form.color,
  borderColor: form.color
}));

function pickRandomColor() {
  form.color = randomMorandiColor(props.usedColors);
}

const save = async () => {
  const name = form.name.trim();
  if (!name) {
    ElMessage.warning("请输入分组名称");
    return;
  }
  const originalName = props.group?.name?.trim().toLowerCase() ?? "";
  const duplicate = props.existingNames.find(
    n =>
      n.trim().toLowerCase() === name.toLowerCase() &&
      n.trim().toLowerCase() !== originalName
  );
  if (duplicate) {
    ElMessage.warning("分组名称已存在，请换一个");
    return;
  }
  loading.value = true;
  try {
    if (isEdit.value && props.group) {
      await updateWatchlistGroup(props.group.id, { name, color: form.color });
      ElMessage.success("分组已更新");
    } else {
      const res = await createWatchlistGroup({ name,  color: form.color });
      const newGroup = (res as { data?: WatchlistGroup })?.data;
      if (newGroup) emit("created", newGroup);
      ElMessage.success("分组已创建");
    }
    emit("saved");
    handleVisibleChange(false);
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { message?: string } } })?.response
      ?.data?.message;
    if (msg && msg.includes("已存在")) {
      ElMessage.warning("该分组名称已存在");
    } else {
      ElMessage.error(isEdit.value ? "更新分组失败" : "创建分组失败");
    }
  } finally {
    loading.value = false;
  }
};
</script>

<style lang="scss" scoped>
.group-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.group-form__label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.group-form__colors {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.color-dot {
  width: 24px;
  height: 24px;
  padding: 0;
  cursor: pointer;
  border: 2px solid transparent;
  border-radius: 50%;
  transition:
    transform 0.15s,
    box-shadow 0.15s;
}

.color-dot:hover {
  transform: scale(1.1);
}

.color-dot--active {
  border-color: var(--text-primary);
  box-shadow: 0 0 0 2px var(--bg-card);
}

.color-dot--random {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  background-color: var(--bg-soft);
  border: 1px dashed var(--border-strong);
}

.group-form__preview {
  margin-top: var(--space-2);
}

.group-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.2;
  border: 1px solid;
  border-radius: var(--radius-pill);
}
</style>
