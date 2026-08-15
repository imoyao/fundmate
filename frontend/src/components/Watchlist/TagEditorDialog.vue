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
        <el-button size="large" @click="tagFormVisible = true">
          <IconifyIconOffline icon="ep:plus" />
        </el-button>
      </div>

      <!-- 新建标签：复用独立子弹窗（TagFormDialog），自带遮罩隔离父弹窗与背景，
           彻底规避此前「行内表单横向挤压 + 按钮悬浮」的布局崩坏。 -->
      <TagFormDialog
        v-model="tagFormVisible"
        :used-colors="tagFormUsedColors"
        @created="onTagFormCreated"
        @saved="onTagFormSaved"
      />
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
  addTagToItem,
  removeTagFromItem,
  type WatchlistItem,
  type WatchlistTag
} from "@/api/watchlist";
import { findTagName, findTagColor } from "@/utils/tagHelpers";
import TagFormDialog from "./TagFormDialog.vue";

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
// 本地可写副本：避免直接 mutate prop（vue/no-mutating-props），
// 展示与移除操作都基于本地副本，保存成功后由父组件刷新 item。
const localTagIds = ref<number[]>([]);
// 新建标签子弹窗（TagFormDialog）显隐：复用独立模态，自带遮罩隔离。
const tagFormVisible = ref(false);

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
      tagFormVisible.value = false;
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

/** 子弹窗已用色：供新建标签随机取色时尽量避开，保持视觉区分度 */
const tagFormUsedColors = computed(() =>
  props.allTags.map(t => t.color).filter((c): c is string => !!c)
);

/** 子弹窗新建标签成功后：自动把新标签加入当前资产的待保存列表 */
function onTagFormCreated(tag: WatchlistTag) {
  if (tag.id) editingItemNewTagIds.value.push(tag.id);
}

/** 子弹窗保存（含新建/编辑）后：通知父组件刷新全部标签，使下拉可选列表同步 */
function onTagFormSaved() {
  emit("saved");
}

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
</style>
