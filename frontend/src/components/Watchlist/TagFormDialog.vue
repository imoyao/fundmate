<!--
  TagFormDialog · 标签新建/编辑轻量弹窗（强制复用，见 docs/design/components.md）
  - 仅负责「单个标签」的名称 + 颜色编辑，与列表管理彻底解耦（参考 GitHub Labels 交互）。
  - 由 TagManagerDialog 在点击「新建标签」或某行「编辑」时调起，回填原 name/color。
  - props：modelValue(显隐)、tag(待编辑标签，null 表示新建)。
  - emits：update:modelValue、saved(保存成功后触发，父组件刷新标签列表)。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="isEdit ? '编辑标签' : '新建标签'"
    width="420px"
    class="tag-form-dialog"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
  >
    <div class="tag-form-body">
      <label class="tag-form-label">名称</label>
      <el-input
        ref="nameInputRef"
        v-model="name"
        placeholder="输入标签名..."
        size="large"
        class="tag-form-input"
        maxlength="20"
        show-word-limit
        @keyup.enter="save"
      />

      <label class="tag-form-label">颜色</label>
      <div class="tag-form-swatches">
        <button
          v-for="c in PRESET_TAG_COLORS"
          :key="c"
          class="color-swatch-btn"
          :class="{ 'is-selected': color === c }"
          :style="{ backgroundColor: c }"
          :aria-label="`颜色 ${c}`"
          @click="color = c"
        />
      </div>
    </div>

    <template #footer>
      <el-button size="large" @click="handleClose">取消</el-button>
      <el-button
        type="primary"
        size="large"
        :loading="saving"
        @click="save"
      >
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from "vue";
import { ElMessage } from "element-plus";
import type { ElInput } from "element-plus";
import {
  createWatchlistTag,
  updateWatchlistTag,
  type WatchlistTag
} from "@/api/watchlist";
import { PRESET_TAG_COLORS, DEFAULT_TAG_COLOR } from "@/constants/watchlist";

const props = defineProps<{
  modelValue: boolean;
  /** 待编辑标签，null 表示新建 */
  tag: WatchlistTag | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const isEdit = computed(() => props.tag !== null);

const name = ref("");
const color = ref(DEFAULT_TAG_COLOR);
const saving = ref(false);
const nameInputRef = ref<InstanceType<typeof ElInput> | null>(null);

// 每次打开时按 tag 回填（编辑）或重置（新建）
watch(
  () => props.modelValue,
  visible => {
    if (visible) {
      name.value = props.tag?.name ?? "";
      color.value = props.tag?.color || DEFAULT_TAG_COLOR;
      nextTick(() => nameInputRef.value?.focus());
    }
  }
);

function handleVisibleChange(value: boolean) {
  emit("update:modelValue", value);
}

function handleClose() {
  emit("update:modelValue", false);
}

const save = async () => {
  const trimmed = name.value.trim();
  if (!trimmed) {
    ElMessage.warning("请输入标签名称");
    return;
  }
  saving.value = true;
  try {
    if (isEdit.value && props.tag) {
      await updateWatchlistTag(props.tag.id, {
        name: trimmed,
        color: color.value
      });
      ElMessage.success("标签已更新");
    } else {
      await createWatchlistTag({ name: trimmed, color: color.value });
      ElMessage.success("标签已创建");
    }
    handleClose();
    emit("saved");
  } catch (e: unknown) {
    const err = e as { response?: { status?: number } };
    if (err?.response?.status === 409) {
      ElMessage.warning("该标签已存在");
    } else {
      ElMessage.error(isEdit.value ? "更新标签失败" : "创建标签失败");
    }
  } finally {
    saving.value = false;
  }
};
</script>

<style lang="scss" scoped>
.tag-form-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.tag-form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.tag-form-input {
  width: 100%;
}

.tag-form-swatches {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

/* 色板按钮（标签选色用，与 TagManagerDialog / TagEditorDialog 保持一致） */
.color-swatch-btn {
  width: 22px;
  height: 22px;
  cursor: pointer;
  border: 2px solid var(--bg-card);
  border-radius: 50%;
  box-shadow: 0 0 0 1px var(--border-light);
  transition: all 0.2s ease;
}

.color-swatch-btn.is-selected {
  border-color: var(--brand-700);
  box-shadow:
    0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);
  transform: scale(1.15);
}

.color-swatch-btn:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);
}
</style>
