<script setup lang="ts">
import { ref } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import type { StrategyTag } from "@/api/strategy";
import type { EnrichedHolding } from "./strategyViewModel";

/**
 * 「策略标签」单元格：已挂标签（可逐个摘除）+ 点击弹出的多选面板（可增删、可新建）。
 *
 * 两处约定：
 * - `createTag` 是**函数 prop 而不是 emit**：新建成功后要清空输入框、失败要保留输入
 *   （让用户重打一遍是纯粹的惩罚）。emit 拿不到处理函数的返回值，函数 prop 可以
 *   `await` 到布尔结果，语义与拆分前一致。
 * - `update-tags` 传的是**勾选后的全集**，由 composable 与当前集合做双向 diff。
 */
defineOptions({ name: "StrategyTagCell" });

const props = defineProps<{
  /** 该行的持仓（含 `_tags`） */
  row: EnrichedHolding;
  /** 全部可选标签 */
  allTags: StrategyTag[];
  /** 新建并绑定标签；返回是否成功 */
  createTag: (name: string) => Promise<boolean>;
}>();

const emit = defineEmits<{
  /** 摘掉一个标签 */
  (e: "unbind", tagName: string): void;
  /** 提交勾选后的全集 */
  (e: "update-tags", tags: string[]): void;
}>();

/** 新建标签输入框（每行各自一份，不再由父层用 id → name 的映射托管） */
const newTagName = ref("");

async function submitNewTag() {
  const name = newTagName.value.trim();
  if (!name) return;
  const ok = await props.createTag(name);
  if (ok) newTagName.value = "";
}
</script>

<template>
  <el-popover
    placement="bottom"
    :width="240"
    trigger="click"
    :teleported="true"
  >
    <template #reference>
      <div class="tag-trigger">
        <template v-if="row._tags && row._tags.length">
          <el-tag
            v-for="tag in row._tags"
            :key="tag"
            size="small"
            class="mr-1 mb-1"
            closable
            @close="emit('unbind', tag)"
            >{{ tag }}</el-tag
          >
        </template>
        <span
          v-else
          class="text-xs"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          未设置
        </span>
        <IconifyIconOffline
          icon="ep:arrow-down"
          class="ml-1 text-xs"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        />
      </div>
    </template>
    <div class="tag-selector">
      <div class="text-xs mb-2" :style="{ color: 'var(--text-secondary)' }">
        为「{{ row.name || row.symbol }}」选择标签
      </div>
      <el-checkbox-group
        :model-value="row._tags || []"
        size="small"
        @update:model-value="(vals: string[]) => emit('update-tags', vals)"
      >
        <el-checkbox
          v-for="tag in allTags"
          :key="tag.id"
          :label="tag.name"
          class="block mb-1"
        />
      </el-checkbox-group>
      <el-input
        v-model="newTagName"
        size="small"
        placeholder="输入新标签名称"
        class="mt-3"
        @keyup.enter="submitNewTag"
      >
        <template #append>
          <el-button @click="submitNewTag">添加</el-button>
        </template>
      </el-input>
    </div>
  </el-popover>
</template>

<style scoped>
/* 标签触发器 */
.tag-trigger {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  min-height: 24px;
  cursor: pointer;
}

.tag-trigger:hover {
  opacity: 0.8;
}

.tag-selector {
  padding: 8px 0;
}

.tag-selector :deep(.el-checkbox) {
  display: block;
  margin-bottom: 4px;
}
</style>
