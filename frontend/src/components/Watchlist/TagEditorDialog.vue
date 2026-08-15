<!--
  TagEditorDialog · 自选行内标签编辑弹窗（强制复用，见 docs/design/components.md）
  - 为单个自选资产添加/移除标签，自 watchlist 页面拆出的共有组件。
  - props：modelValue(显隐)、item(当前自选资产)、allTags(全部标签)。
  - emits：update:modelValue、saved(保存成功后触发，父组件负责刷新列表与标签)。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑标签"
    width="420px"
    @update:model-value="handleVisibleChange"
  >
    <div class="mb-4">
      <span class="text-sm" :style="{ color: 'var(--text-secondary)' }">
        为
        <strong>{{ item?.display_name || item?.symbol }}</strong>
        添加或移除标签
      </span>
    </div>

    <div v-if="item && localTagIds.length > 0" class="mb-4">
      <span class="tag-hint block mb-2">已有标签</span>
      <div class="flex flex-wrap gap-2">
        <el-tag
          v-for="tagId in localTagIds"
          :key="tagId"
          size="small"
          closable
          :style="{
            backgroundColor: findTagColor(allTags, tagId) + '20',
            color: 'var(--text-primary)',
            border: '1px solid ' + findTagColor(allTags, tagId)
          }"
          @close="removeTagFromEditingItem(tagId)"
        >
          {{ findTagName(allTags, tagId) }}
        </el-tag>
      </div>
    </div>

    <div class="mb-4">
      <span class="tag-hint block mb-2">添加标签</span>
      <div class="flex gap-2">
        <el-select
          v-model="editingItemNewTagIds"
          multiple
          filterable
          placeholder="选择标签"
          class="flex-1"
          size="large"
        >
          <el-option
            v-for="tag in availableTags"
            :key="tag.id"
            :label="tag.name"
            :value="tag.id"
          >
            <div class="flex items-center gap-2">
              <!-- 数据色例外：标签色为用户数据（非设计令牌），缺失时回退中性 token -->
              <span
                class="w-3 h-3 rounded-full"
                :style="{
                  backgroundColor: tag.color || 'var(--text-tertiary)'
                }"
              />
              <span>{{ tag.name }}</span>
            </div>
          </el-option>
        </el-select>
        <el-button size="large" @click="showNewTagFormInEditor = true">
          <IconifyIconOffline icon="ep:plus" />
        </el-button>
      </div>

      <div
        v-if="showNewTagFormInEditor"
        class="mt-2 p-3 rounded-lg flex items-end gap-2"
        :style="{ backgroundColor: 'var(--bg-warm)' }"
      >
        <el-input
          v-model="newTagNameInEditor"
          placeholder="标签名"
          size="large"
          class="w-24"
        />
        <div class="flex gap-1">
          <button
            v-for="c in PRESET_TAG_COLORS"
            :key="c"
            class="color-swatch-btn"
            :class="{ 'is-selected': newTagColorInEditor === c }"
            :style="{ backgroundColor: c }"
            @click="newTagColorInEditor = c"
          />
        </div>
        <el-button type="primary" size="large" @click="createTagInEditor"
          >确定</el-button
        >
        <el-button size="large" @click="showNewTagFormInEditor = false"
          >取消</el-button
        >
      </div>
    </div>

    <template #footer>
      <el-button size="large" @click="handleClose">取消</el-button>
      <el-button
        type="primary"
        size="large"
        :loading="savingTags"
        @click="saveTagChanges"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import {
  createWatchlistTag,
  addTagToItem,
  removeTagFromItem,
  type WatchlistItem,
  type WatchlistTag
} from "@/api/watchlist";
import { PRESET_TAG_COLORS, DEFAULT_TAG_COLOR } from "@/constants/watchlist";
import { findTagName, findTagColor } from "@/utils/tagHelpers";

const props = defineProps<{
  modelValue: boolean;
  item: WatchlistItem | null;
  allTags: WatchlistTag[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const editingItemNewTagIds = ref<number[]>([]);
const savingTags = ref(false);
const showNewTagFormInEditor = ref(false);
const newTagNameInEditor = ref("");
const newTagColorInEditor = ref(DEFAULT_TAG_COLOR);
// 本地可写副本：避免直接 mutate prop（vue/no-mutating-props），
// 展示与移除操作都基于本地副本，保存成功后由父组件刷新 item。
const localTagIds = ref<number[]>([]);

/** 未添加到当前资产的可选标签 */
const availableTags = computed(() => {
  if (!props.item) return props.allTags;
  const existingIds = new Set(localTagIds.value);
  return props.allTags.filter(t => !existingIds.has(t.id));
});

// 每次打开时重置新增态
watch(
  () => props.modelValue,
  visible => {
    if (visible) {
      localTagIds.value = [...(props.item?.tag_ids ?? [])];
      editingItemNewTagIds.value = [];
      showNewTagFormInEditor.value = false;
      newTagNameInEditor.value = "";
      newTagColorInEditor.value = DEFAULT_TAG_COLOR;
    }
  }
);

function handleVisibleChange(value: boolean) {
  emit("update:modelValue", value);
}

function handleClose() {
  emit("update:modelValue", false);
}

const removeTagFromEditingItem = async (tagId: number) => {
  if (!props.item) return;
  try {
    await removeTagFromItem(props.item.id, tagId);
    localTagIds.value = localTagIds.value.filter(id => id !== tagId);
    ElMessage.success("标签已移除");
  } catch (e: unknown) {
    ElMessage.error("移除标签失败");
  }
};

const createTagInEditor = async () => {
  if (!newTagNameInEditor.value.trim()) return;
  try {
    const res = await createWatchlistTag({
      name: newTagNameInEditor.value.trim(),
      color: newTagColorInEditor.value
    });
    const newTag = (res as { data?: WatchlistTag })?.data;
    if (!newTag) return;
    editingItemNewTagIds.value.push(newTag.id);
    showNewTagFormInEditor.value = false;
    newTagNameInEditor.value = "";
    // 通知父组件刷新标签列表（保持内存与后端一致）
    emit("saved");
  } catch (e: unknown) {
    const err = e as { response?: { status?: number } };
    if (err?.response?.status === 409) {
      ElMessage.warning("该标签已存在");
    } else {
      ElMessage.error("创建标签失败");
    }
  }
};

const saveTagChanges = async () => {
  if (!props.item) return;
  savingTags.value = true;
  try {
    const itemId = props.item.id;
    for (const tagId of editingItemNewTagIds.value) {
      await addTagToItem(itemId, tagId);
    }
    ElMessage.success("标签已更新");
    handleClose();
    emit("saved");
  } catch (e: unknown) {
    ElMessage.error("保存标签失败");
  } finally {
    savingTags.value = false;
  }
};
</script>

<style lang="scss" scoped>
.tag-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 行内标签编辑弹窗内的小色板按钮 */
.color-swatch-btn {
  width: 20px;
  height: 20px;
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
</style>
