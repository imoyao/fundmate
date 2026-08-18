<!--
  GroupManagerDialog · 自选分组管理弹窗（强制复用，见 docs/design/components.md）
  - GitHub Labels 风格：白底卡片列表 + 顶部搜索/新建，与「表单填写」彻底解耦。
  - 列表只负责展示：名称胶囊（颜色底）、系统分组标识、hover 行内「编辑/删除」。
  - 新建/编辑由 GroupFormDialog 轻量弹窗承担（点击「新建分组」或某行「编辑」调起）。
  - props：modelValue(显隐)、allGroups(全部分组，含系统分组)。
  - emits：update:modelValue、groups-changed(增删改分组后触发，父组件刷新分组列表)。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="管理分组"
    width="640px"
    class="group-manager-dialog"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
  >
    <div class="group-manager-header">
      <el-input
        v-model="keyword"
        placeholder="搜索分组..."
        size="large"
        class="group-search"
        clearable
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-button
        type="primary"
        size="large"
        class="group-create-btn"
        @click="openCreate"
      >
        <el-icon class="mr-1"><Plus /></el-icon> 新建分组
      </el-button>
    </div>

    <div class="group-list-card">
      <div v-if="filteredGroups.length === 0" class="group-empty">
        {{ keyword ? "未找到匹配的分组" : "暂无分组，点击右上角「新建分组」" }}
      </div>
      <ul v-else class="group-list">
        <li
          v-for="group in filteredGroups"
          :key="group.id ?? group.key"
          class="group-row"
          :class="{ 'group-row--system': group.is_system }"
        >
          <span class="group-pill" :style="pillStyle(group.color)">
            {{ group.name }}
          </span>

          <span v-if="group.is_system" class="group-badge">系统分组</span>
          <!-- 自定义分组显示资产数量；后端 build_groups_data() 已返回 count 字段，
               勿改回硬编码字符串（原 "自定义" 无信息量，已替换为动态计数）。 -->
          <span v-else class="group-stat">{{ group.count ?? 0 }} 项</span>

          <div class="group-row__actions">
            <el-button
              size="small"
              text
              bg
              :disabled="group.is_system"
              @click="openEdit(group)"
            >
              <el-icon class="mr-1"><Edit /></el-icon>编辑
            </el-button>
            <el-popconfirm
              title="确定删除该分组？"
              :disabled="group.is_system"
              @confirm="deleteGroup(group.id)"
            >
              <template #reference>
                <el-button
                  size="small"
                  text
                  bg
                  type="danger"
                  :disabled="group.is_system"
                  :title="group.is_system ? '系统分组不可删除' : ''"
                >
                  <el-icon class="mr-1"><Delete /></el-icon>删除
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </li>
      </ul>
    </div>

    <GroupFormDialog
      v-model="showForm"
      :group="editingGroup"
      :used-colors="usedColors"
      @saved="onFormSaved"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { ElMessage } from "element-plus";
import { Edit, Delete, Plus, Search } from "@element-plus/icons-vue";
import type { WatchlistGroup } from "@/api/watchlist";
import { deleteWatchlistGroup } from "@/api/watchlist";
import GroupFormDialog from "./GroupFormDialog.vue";

const props = defineProps<{
  modelValue: boolean;
  allGroups: WatchlistGroup[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "groups-changed"): void;
}>();

const keyword = ref("");
const showForm = ref(false);
const editingGroup = ref<WatchlistGroup | null>(null);

const filteredGroups = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return props.allGroups;
  return props.allGroups.filter(g => g.name.toLowerCase().includes(kw));
});

const usedColors = computed(
  () => props.allGroups.map(g => g.color).filter(Boolean) as string[]
);

function pillStyle(color: string | null) {
  const c = color || "#e07a6b";
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
  editingGroup.value = null;
  showForm.value = true;
}

function openEdit(group: WatchlistGroup) {
  if (group.is_system) return;
  editingGroup.value = group;
  showForm.value = true;
}

function onFormSaved() {
  emit("groups-changed");
}

const deleteGroup = async (groupId: number) => {
  try {
    await deleteWatchlistGroup(groupId);
    ElMessage.success("分组已删除");
    emit("groups-changed");
  } catch (e: unknown) {
    ElMessage.error("删除分组失败");
  }
};
</script>

<style lang="scss" scoped>
.group-manager-header {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-3);
}

.group-search {
  flex: 1;
  min-width: 0;
}

.group-search :deep(.el-input__wrapper) {
  border-radius: var(--radius-pill);
}

.group-create-btn {
  flex-shrink: 0;
}

.group-list-card {
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}

.group-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.group-empty {
  padding: var(--space-standard);
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}

.group-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  min-height: 46px;
  padding: 0 var(--space-3);
  border-bottom: 1px solid var(--border-light);
  transition: background-color 0.2s;
}

.group-row:last-child {
  border-bottom: none;
}

.group-row:hover {
  background-color: var(--bg-soft);
}

.group-pill {
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

.group-badge {
  flex-shrink: 0;
  padding: 2px 8px;
  font-size: 12px;
  color: var(--text-tertiary);
  background-color: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
}

.group-stat {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

.group-row__actions {
  display: flex;
  flex-shrink: 0;
  gap: var(--space-2);
  align-items: center;
  margin-left: auto;
  opacity: 0;
  transition: opacity 0.2s;
}

.group-row:hover .group-row__actions {
  opacity: 1;
}
</style>
