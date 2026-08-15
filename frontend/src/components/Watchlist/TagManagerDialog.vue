<!--
  TagManagerDialog · 自选标签管理弹窗（强制复用，见 docs/design/components.md）
  - 选择/编辑/新建/删除标签，自 watchlist 页面拆出的共有组件。
  - props：modelValue(显隐)、allTags(全部标签)、usedTagIds(被使用中的标签 id，用于禁止删除)。
  - emits：update:modelValue、tags-changed(增删改标签后触发，父组件刷新标签列表)。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="管理标签"
    width="560px"
    class="tag-manager-dialog"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
  >
    <div class="tag-manager-body">
      <!-- 1. 全部标签列表（直接展示，便于管理） -->
      <div class="mb-4">
        <div class="tag-section-title">
          全部标签（{{ allTags.length }}）
          <span v-if="allTags.length === 0" class="tag-section-hint ml-1"
            >暂无标签，可在下方新建</span
          >
        </div>
        <div class="tag-list">
          <div
            v-for="tag in allTags"
            :key="tag.id"
            class="tag-row"
            :class="{ 'tag-row--editing': editingTagId === tag.id }"
            @click="selectTagForEdit(tag.id)"
          >
            <span class="tag-row__name">
              <!-- 数据色例外：标签色为用户数据（非设计令牌），缺失时回退中性 token -->
              <span
                class="tag-row__dot"
                :style="{
                  backgroundColor: tag.color || 'var(--text-tertiary)'
                }"
              />
              <span>{{ tag.name }}</span>
            </span>
            <!-- 操作图标：默认隐藏，hover 行时显现，避免列表视觉杂乱 -->
            <div class="tag-row__actions">
              <el-icon
                class="tag-row__edit"
                @click.stop="selectTagForEdit(tag.id)"
              >
                <Edit />
              </el-icon>
              <el-popconfirm
                title="确定删除该标签？"
                :disabled="usedTagIds.has(tag.id)"
                @confirm="deleteTag(tag.id)"
              >
                <template #reference>
                  <el-icon
                    class="tag-row__delete"
                    :class="{ 'is-disabled': usedTagIds.has(tag.id) }"
                    @click.stop
                  >
                    <Delete />
                  </el-icon>
                </template>
              </el-popconfirm>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. 新建/编辑表单区域（米色卡片，拆分多行） -->
      <div class="tag-form-area">
        <!-- 小标题：区分「编辑」与「新建」状态 -->
        <div class="tag-form-title">
          {{ editingTagId ? "编辑标签" : "新建标签" }}
          <span v-if="editingTagId" class="tag-form-title__sub"
            >· {{ editTagName || "未命名" }}</span
          >
        </div>

        <!-- 行1：名称输入 + 保存/添加按钮 -->
        <div class="tag-form-row tag-form-row--main">
          <el-input
            v-if="editingTagId"
            ref="editInputRef"
            v-model="editTagName"
            placeholder="修改标签名称..."
            size="large"
            class="tag-form-input"
            @keyup.enter="saveEditTag(editingTagId)"
          />
          <el-input
            v-else
            v-model="newTagNameInManager"
            placeholder="输入新标签名..."
            size="large"
            class="tag-form-input"
            @keyup.enter="addNewTagInManager"
          />
          <el-button
            v-if="editingTagId"
            type="primary"
            size="large"
            class="tag-form-action"
            @click="saveEditTag(editingTagId)"
          >
            保存修改
          </el-button>
          <el-button
            v-else
            type="primary"
            size="large"
            class="tag-form-action"
            @click="addNewTagInManager"
          >
            添加标签
          </el-button>
        </div>

        <!-- 行2：颜色选择（选中态用 --brand-700 描边，不与输入红框冲突） -->
        <div class="tag-form-row tag-form-row--colors">
          <span class="tag-form-label">颜色</span>
          <div class="tag-form-swatches">
            <button
              v-for="c in PRESET_TAG_COLORS"
              :key="c"
              class="color-swatch-btn"
              :class="{
                'is-selected': editingTagId
                  ? editTagColor === c
                  : newTagColorInManager === c
              }"
              :style="{ backgroundColor: c }"
              @click="
                editingTagId ? (editTagColor = c) : (newTagColorInManager = c)
              "
            />
          </div>
        </div>

        <!-- 行3：删除（仅编辑态，置于左下） -->
        <div v-if="editingTagId" class="tag-form-row tag-form-row--delete">
          <el-popconfirm
            title="确定要删除该标签吗？"
            @confirm="deleteTag(editingTagId)"
          >
            <template #reference>
              <el-button type="danger" link size="small">
                <el-icon class="mr-1"><Delete /></el-icon> 删除此标签
              </el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from "vue";
import { ElMessage } from "element-plus";
import { Edit, Delete } from "@element-plus/icons-vue";
import type { ElInput } from "element-plus";
import {
  createWatchlistTag,
  updateWatchlistTag,
  deleteWatchlistTag,
  type WatchlistTag
} from "@/api/watchlist";
import { PRESET_TAG_COLORS, DEFAULT_TAG_COLOR } from "@/constants/watchlist";
import { findTagName, findTagColor } from "@/utils/tagHelpers";

const props = defineProps<{
  modelValue: boolean;
  allTags: WatchlistTag[];
  /** 正被资产使用的标签 id（禁止删除，父组件基于当前列表计算） */
  usedTagIds: Set<number>;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "tags-changed"): void;
}>();

const editingTagId = ref<number | null>(null);
const editTagName = ref("");
const editTagColor = ref(DEFAULT_TAG_COLOR);
const editInputRef = ref<InstanceType<typeof ElInput> | null>(null);
const newTagNameInManager = ref("");
const newTagColorInManager = ref(DEFAULT_TAG_COLOR);

// 每次打开时重置编辑态
watch(
  () => props.modelValue,
  visible => {
    if (visible) {
      editingTagId.value = null;
      editTagName.value = "";
      newTagNameInManager.value = "";
      newTagColorInManager.value = DEFAULT_TAG_COLOR;
    }
  }
);

function handleVisibleChange(value: boolean) {
  emit("update:modelValue", value);
}

const selectTagForEdit = (tagId: number) => {
  const tag = props.allTags.find(t => t.id === tagId);
  if (!tag) return;

  if (editingTagId.value === tagId) {
    editingTagId.value = null;
    editTagName.value = "";
    return;
  }

  editingTagId.value = tagId;
  editTagName.value = tag.name;
  editTagColor.value = tag.color || DEFAULT_TAG_COLOR;

  nextTick(() => {
    editInputRef.value?.focus();
  });
};

const addNewTagInManager = async () => {
  if (!newTagNameInManager.value.trim()) return;
  try {
    const res = await createWatchlistTag({
      name: newTagNameInManager.value.trim(),
      color: newTagColorInManager.value
    });
    const newTag = (res as { data?: WatchlistTag })?.data;
    if (!newTag) return;
    // 新建后直接进入编辑态，便于继续调整名称/颜色
    editingTagId.value = newTag.id;
    editTagName.value = newTag.name;
    editTagColor.value = newTag.color || DEFAULT_TAG_COLOR;
    emit("tags-changed");
    newTagNameInManager.value = "";
    newTagColorInManager.value = DEFAULT_TAG_COLOR;
    ElMessage.success(`标签「${newTag.name}」已创建`);
    nextTick(() => {
      editInputRef.value?.focus();
    });
  } catch (e: unknown) {
    const err = e as { response?: { status?: number } };
    if (err?.response?.status === 409) {
      ElMessage.warning("该标签已存在");
    } else {
      ElMessage.error("创建标签失败");
    }
  }
};

const saveEditTag = async (tagId: number) => {
  const originalTag = props.allTags.find(t => t.id === tagId);
  if (!originalTag) return;
  const newName = editTagName.value.trim();
  if (!newName) {
    ElMessage.warning("请输入标签名称");
    editTagName.value = originalTag.name;
    return;
  }
  if (
    newName === originalTag.name &&
    editTagColor.value === (originalTag.color || DEFAULT_TAG_COLOR)
  ) {
    editingTagId.value = null;
    return;
  }
  try {
    await updateWatchlistTag(tagId, {
      name: newName,
      color: editTagColor.value
    });
    ElMessage.success("标签已更新");
    editingTagId.value = null;
    editTagName.value = "";
    emit("tags-changed");
  } catch (e: unknown) {
    const err = e as { response?: { status?: number } };
    if (err?.response?.status === 409) {
      ElMessage.warning("标签名称已存在");
      editTagName.value = originalTag.name;
    } else {
      ElMessage.error("更新标签失败");
    }
  }
};

const deleteTag = async (tagId: number) => {
  if (props.usedTagIds.has(tagId)) {
    ElMessage.warning("该标签正被使用，无法删除");
    return;
  }
  try {
    await deleteWatchlistTag(tagId);
    ElMessage.success("标签已删除");
    if (editingTagId.value === tagId) {
      editingTagId.value = null;
      editTagName.value = "";
    }
    emit("tags-changed");
  } catch (e: unknown) {
    ElMessage.error("删除标签失败");
  }
};
</script>

<style lang="scss" scoped>
.tag-section-title {
  margin-bottom: var(--space-2);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}

.tag-section-hint {
  margin-bottom: var(--space-2);
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 全部标签列表 */
.tag-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-height: 280px;
  overflow-y: auto;
  padding-right: var(--space-2);
}

.tag-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition:
    border-color 0.2s,
    background-color 0.2s;
}

.tag-row:hover {
  border-color: var(--brand-700);
  background-color: var(--bg-hover);
}

.tag-row--editing {
  border-color: var(--brand-700);
  box-shadow: var(--focus-ring);
}

.tag-row__name {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: 1;
  font-size: 14px;
  color: var(--text-primary);
}

.tag-row__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

/* 操作图标容器：默认隐藏，hover 行或处于编辑态时显现 */
.tag-row__actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  opacity: 0;
  transition: opacity 0.2s;
}

.tag-row:hover .tag-row__actions,
.tag-row--editing .tag-row__actions {
  opacity: 1;
}

.tag-row__edit {
  cursor: pointer;
  color: var(--text-tertiary);
  transition: color 0.2s;
}

.tag-row__edit:hover {
  color: var(--brand-700);
}

.tag-row__delete {
  cursor: pointer;
  color: var(--text-tertiary);
  transition: color 0.2s;
}

.tag-row__delete:hover {
  color: var(--color-danger-system);
}

.tag-row__delete.is-disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

/* 新建/编辑表单卡片（米色区域，含标题与分割线） */
.tag-form-area {
  padding: var(--space-standard);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--bg-warm);
}

.tag-form-title {
  margin-bottom: var(--space-3);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.tag-form-title__sub {
  margin-left: var(--space-1);
  font-weight: 400;
  color: var(--text-tertiary);
}

.tag-form-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.tag-form-row + .tag-form-row {
  margin-top: var(--space-3);
}

.tag-form-row--main {
  align-items: stretch;
}

.tag-form-input {
  flex: 1;
  min-width: 150px;
}

/* 输入框默认中性边框，避免与校验红框混淆；聚焦用品牌色描边 */
.tag-form-input :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--border-default) inset;
}

.tag-form-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--brand-700) inset;
}

.tag-form-action {
  flex-shrink: 0;
}

.tag-form-label {
  flex-shrink: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.tag-form-row--colors {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background-color: var(--bg-soft);
}

.tag-form-swatches {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

/* 色板按钮（标签新建/编辑选色用） */
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

.color-swatch-btn:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);
}
</style>
