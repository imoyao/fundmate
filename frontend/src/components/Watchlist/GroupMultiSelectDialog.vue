<!--
  GroupMultiSelectDialog · 行操作列「加入分组」弹层（#1449 多分组管理）

  与 GroupItemsDialog（管理某个分组的成员）的分工：
  - GroupItemsDialog：从分组视角，增删某自定义分组的成员（抽屉双栏）；
  - 本弹层：从「单个产品」视角，勾选它应属于哪些自定义分组（可多选），
    后端 add_item_to_group / remove_item_to_group 已幂等支持，一个产品可同时属于多组。

  交互：勾选即生效（无保存按钮），乐观同步 item.group_ids 使列表「所属分组」列即时更新。
  props：modelValue(显隐)、item(目标产品)、groups(自定义分组列表，由父传入)。
  emits：update:modelValue、changed(增删成功后触发，父刷新分组计数与列表)。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="加入分组"
    width="420px"
    class="group-multi-dialog"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
  >
    <div v-loading="loading" class="gm-body">
      <p v-if="item" class="gm-hint">
        将「<span class="gm-item">{{ item.display_name }}</span
        >」加入以下自定义分组（可多选）：
      </p>
      <p v-else class="gm-hint">请先选择一个产品</p>
      <ul v-if="groups.length" class="gm-list">
        <li v-for="g in groups" :key="g.id" class="gm-row">
          <el-checkbox
            :model-value="isMember(g.id)"
            :disabled="loading"
            @change="(val: unknown) => toggle(g.id, val)"
          >
            <span class="gm-name">{{ g.name }}</span>
          </el-checkbox>
        </li>
      </ul>
      <p v-else class="gm-empty">暂无自定义分组，请先在分组栏新建</p>
    </div>
    <template #footer>
      <el-button @click="close">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import {
  addItemToGroup,
  removeItemFromGroup,
  type WatchlistItem,
  type WatchlistGroup
} from "@/api/watchlist";

const props = defineProps<{
  modelValue: boolean;
  item: WatchlistItem | null;
  groups: WatchlistGroup[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "changed"): void;
}>();

const loading = ref(false);

/** 当前产品是否已在该分组（按 item.group_ids，与列表「所属分组」列同源） */
function isMember(gid: number): boolean {
  return props.item?.group_ids?.includes(gid) ?? false;
}

async function toggle(gid: number, checked: unknown): Promise<void> {
  const item = props.item;
  if (!item || item.id == null) return;
  const on = Boolean(checked);
  loading.value = true;
  try {
    if (on) {
      await addItemToGroup(item.id, gid);
    } else {
      await removeItemFromGroup(item.id, gid);
    }
    // 乐观同步：直接改行对象 group_ids，使列表「所属分组」列与弹层勾选即时一致
    const ids = item.group_ids ?? [];
    item.group_ids = on
      ? Array.from(new Set([...ids, gid]))
      : ids.filter(id => id !== gid);
    emit("changed");
  } catch (e: unknown) {
    // 已在该组（409）视为成功，其余报错提示
    const status = (e as { response?: { status?: number } })?.response?.status;
    if (status !== 409) {
      ElMessage.error(on ? "加入分组失败，请重试" : "移出分组失败，请重试");
      console.error("切换产品分组失败：", e);
    }
  } finally {
    loading.value = false;
  }
}

function handleVisibleChange(value: boolean): void {
  emit("update:modelValue", value);
}

function close(): void {
  emit("update:modelValue", false);
}
</script>

<style scoped>
.gm-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.gm-hint {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.gm-item {
  font-weight: 600;
  color: var(--text-primary);
}

.gm-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  max-height: 50vh;
  padding: 0;
  margin: 0;
  overflow-y: auto;
  list-style: none;
}

.gm-row {
  padding: var(--space-1) var(--space-2);
  background-color: var(--bg-card);
  border-radius: var(--radius-sm);
}

.gm-name {
  font-size: 13px;
  color: var(--text-primary);
}

.gm-empty {
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}
</style>
