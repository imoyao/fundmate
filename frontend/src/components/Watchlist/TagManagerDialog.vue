<!--
  TagManagerDialog · 自选标签管理弹窗（强制复用，见 docs/design/components.md）
  - GitHub Labels 风格：白底卡片列表 + 顶部搜索/新建，与「表单填写」彻底解耦。
  - 列表只负责展示：名称胶囊（颜色底）、使用统计、hover 行内「编辑/删除」。
  - 新建/编辑由 TagFormDialog 轻量弹窗承担（点击「新建标签」或某行「编辑」调起）。
  - props：modelValue(显隐)、allTags(全部标签)、tagUsage(标签→使用计数 Map，>0 表示被资产使用、禁止删除)。
  - emits：update:modelValue、tags-changed(增删改标签后触发，父组件刷新标签列表)。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="管理标签"
    width="640px"
    class="tag-manager-dialog"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
  >
    <!-- 顶部：搜索 + 新建（替代原底部拥挤操作区） -->
    <div class="tag-manager-header">
      <el-input
        v-model="keyword"
        placeholder="搜索标签..."
        size="large"
        class="tag-search"
        clearable
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- 列表（白底卡片，行间 --border-light 浅色分割线） -->
    <div class="tag-list-card">
      <div v-if="filteredTags.length === 0" class="tag-empty">
        {{ keyword ? "未找到匹配的标签" : "暂无标签，点击右上角「新建标签」" }}
      </div>
      <ul v-else class="tag-list">
        <li
          v-for="tag in filteredTags"
          :key="tag.id"
          class="tag-row"
          :class="{ 'tag-row--used': usageOf(tag.id) > 0 }"
        >
          <!-- 名称胶囊：标签色为底，延续设计语言的 --radius-pill -->
          <span class="tag-pill" :style="pillStyle(tag.color)">
            {{ tag.name }}
          </span>

          <!-- 使用统计 -->
          <span class="tag-stat"> {{ usageOf(tag.id) }} 个资产 </span>

          <!-- 行内操作：默认隐藏，hover 行时显现 -->
          <div class="tag-row__actions">
            <el-button size="small" text bg @click="openEdit(tag)">
              <el-icon class="mr-1"><Edit /></el-icon>编辑
            </el-button>
            <el-popconfirm
              title="确定删除该标签？"
              :disabled="usageOf(tag.id) > 0"
              @confirm="deleteTag(tag.id)"
            >
              <template #reference>
                <el-button
                  size="small"
                  text
                  bg
                  type="danger"
                  :disabled="usageOf(tag.id) > 0"
                  :title="usageOf(tag.id) > 0 ? '该标签正被使用，无法删除' : ''"
                >
                  <el-icon class="mr-1"><Delete /></el-icon>删除
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </li>
        <!-- 新建标签：置于列表末尾，紧挨标签名（GitHub Labels 风格），替代顶部按钮 -->
        <li class="tag-row tag-row--create" @click="openCreate">
          <el-icon class="mr-1"><Plus /></el-icon>
          新建标签
        </li>
      </ul>
    </div>

    <!-- 新建/编辑标签的轻量小弹窗（与列表解耦） -->
    <TagFormDialog v-model="showForm" :tag="editingTag" @saved="onFormSaved" />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { ElMessage } from "element-plus";
import { Edit, Delete, Plus, Search } from "@element-plus/icons-vue";
import type { WatchlistTag } from "@/api/watchlist";
import { deleteWatchlistTag } from "@/api/watchlist";
import { DEFAULT_TAG_COLOR } from "@/constants/watchlist";
import TagFormDialog from "./TagFormDialog.vue";

const props = defineProps<{
  modelValue: boolean;
  allTags: WatchlistTag[];
  /** 标签 id → 使用计数（被多少资产引用）；>0 表示被使用、禁止删除 */
  tagUsage: Map<number, number>;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "tags-changed"): void;
}>();

const keyword = ref("");
const showForm = ref(false);
const editingTag = ref<WatchlistTag | null>(null);

const filteredTags = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return props.allTags;
  return props.allTags.filter(t => t.name.toLowerCase().includes(kw));
});

function usageOf(id: number): number {
  return props.tagUsage.get(id) || 0;
}

/** 胶囊底色：标签色 + 低透明度底，文字用原色，缺失回退中性 token */
function pillStyle(color: string | null) {
  const c = color || DEFAULT_TAG_COLOR;
  return {
    backgroundColor: `${c}22`,
    color: c,
    borderColor: c
  };
}

function handleVisibleChange(value: boolean) {
  emit("update:modelValue", value);
}

function openCreate() {
  editingTag.value = null;
  showForm.value = true;
}

function openEdit(tag: WatchlistTag) {
  editingTag.value = tag;
  showForm.value = true;
}

function onFormSaved() {
  emit("tags-changed");
}

const deleteTag = async (tagId: number) => {
  if (usageOf(tagId) > 0) {
    ElMessage.warning("该标签正被使用，无法删除");
    return;
  }
  try {
    await deleteWatchlistTag(tagId);
    ElMessage.success("标签已删除");
    emit("tags-changed");
  } catch (e: unknown) {
    ElMessage.error("删除标签失败");
  }
};
</script>

<style lang="scss" scoped>
/* 顶部：搜索（胶囊）+ 新建 */
.tag-manager-header {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-3);
}

.tag-search {
  flex: 1;
  min-width: 0;
}

.tag-search :deep(.el-input__wrapper) {
  border-radius: var(--radius-pill);
}

/* 列表末尾「新建标签」行：与标签行同高、紧挨列表，hover 提亮为品牌色 */
.tag-row--create {
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  border-bottom: none;
  transition: color 150ms ease;
}

.tag-row--create:hover {
  color: var(--brand-700);
  background-color: var(--bg-soft);
}

/* 列表卡片：白底 + 浅色边框 + 大圆角 */
.tag-list-card {
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}

.tag-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.tag-empty {
  padding: var(--space-standard);
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}

.tag-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  min-height: 46px;
  padding: 0 var(--space-3);
  border-bottom: 1px solid var(--border-light);
  transition: background-color 0.2s;
}

.tag-row:last-child {
  border-bottom: none;
}

.tag-row:hover {
  background-color: var(--bg-soft);
}

/* 名称胶囊：--radius-pill，标签色为底 */
.tag-pill {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  max-width: 240px;
  padding: 4px 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
  border: 1px solid;
  border-radius: var(--radius-pill);
}

/* 使用统计 */
.tag-stat {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

/* 行内操作：默认隐藏，hover 显现 */
.tag-row__actions {
  display: flex;
  flex-shrink: 0;
  gap: var(--space-2);
  align-items: center;
  margin-left: auto;
  opacity: 0;
  transition: opacity 0.2s;
}

.tag-row:hover .tag-row__actions {
  opacity: 1;
}
</style>
