<!--
  TagFormDialog · 标签新建/编辑轻量弹窗（强制复用，见 docs/design/components.md）
  - 仅承载「表单填写」：名称输入 + 莫兰迪色板点选 + 受控随机取色。
  - 列表展示交给 TagManagerDialog（GitHub Labels 风格），二者彻底解耦。
  - props：modelValue(显隐)、tag(传入则为编辑、null 为新建)、usedColors(已用色，用于随机取色避开)。
  - emits：update:modelValue、saved(保存成功)。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="isEdit ? '编辑标签' : '新建标签'"
    width="440px"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
  >
    <div class="tag-form">
      <label class="tag-form__label">名称</label>
      <el-input
        v-model="form.name"
        placeholder="请输入标签名称"
        size="large"
        maxlength="20"
        show-word-limit
        :disabled="loading"
      />

      <label class="tag-form__label">颜色</label>
      <div class="tag-form__colors">
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
          title="随机一个区分度高的颜色"
          @click="pickRandomColor"
        >
          <el-icon><Refresh /></el-icon>
        </button>
      </div>

      <!-- 名称预览胶囊 -->
      <div class="tag-form__preview">
        <span class="tag-pill" :style="pillStyle">{{
          form.name || "标签预览"
        }}</span>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleVisibleChange(false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="save"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import type { WatchlistTag } from "@/api/watchlist";
import { createWatchlistTag, updateWatchlistTag } from "@/api/watchlist";
import {
  PRESET_TAG_COLORS,
  DEFAULT_TAG_COLOR,
  randomMorandiColor
} from "@/constants/watchlist";

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    /** 传入则编辑该标签，null/undefined 为新建 */
    tag?: WatchlistTag | null;
    /** 已占用颜色（用于随机取色时尽量避开） */
    usedColors?: string[];
  }>(),
  { tag: null, usedColors: () => [] }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const loading = ref(false);
const form = reactive<{ name: string; color: string }>({
  name: "",
  color: DEFAULT_TAG_COLOR
});
const isEdit = computed(() => !!props.tag?.id);

watch(
  () => props.modelValue,
  visible => {
    if (visible) {
      form.name = props.tag?.name || "";
      form.color = props.tag?.color || DEFAULT_TAG_COLOR;
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
    ElMessage.warning("请输入标签名称");
    return;
  }
  loading.value = true;
  try {
    if (isEdit.value && props.tag) {
      await updateWatchlistTag(props.tag.id, { name, color: form.color });
      ElMessage.success("标签已更新");
    } else {
      await createWatchlistTag({ name, color: form.color });
      ElMessage.success("标签已创建");
    }
    emit("saved");
    handleVisibleChange(false);
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { message?: string } } })?.response
      ?.data?.message;
    if (msg && msg.includes("已存在")) {
      ElMessage.warning("该标签名称已存在");
    } else {
      ElMessage.error(isEdit.value ? "更新标签失败" : "创建标签失败");
    }
  } finally {
    loading.value = false;
  }
};
</script>

<style lang="scss" scoped>
.tag-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.tag-form__label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.tag-form__colors {
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

.tag-form__preview {
  margin-top: var(--space-2);
}

.tag-pill {
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
