<template>
  <!-- 置顶开关 -->
  <div v-if="showPin" class="mt-3 flex items-center justify-between">
    <span class="text-xs" :style="{ color: 'var(--text-secondary)' }"
      >置顶到首页</span
    >
    <el-switch v-model="pinToTopModel" size="small" />
  </div>

  <!-- 分组选择 -->
  <div class="mt-3">
    <span class="text-xs mb-1 block" :style="{ color: 'var(--text-secondary)' }"
      >加入分组（可选）</span
    >
    <div class="flex gap-2">
      <el-select
        ref="groupSelectRef"
        v-model="groupIdsModel"
        multiple
        filterable
        placeholder="选择分组"
        class="w-full"
        size="small"
        @change="handleGroupSelect"
      >
        <el-option
          v-for="g in groups"
          :key="g.id"
          :label="g.name"
          :value="g.id"
        >
          <div class="flex items-center gap-2">
            <span
              class="w-3 h-3 rounded-full"
              :style="{
                backgroundColor: g.color || 'var(--text-disabled)'
              }"
            />
            <span>{{ g.name }}</span>
          </div>
        </el-option>
      </el-select>
      <el-button
        aria-label="新建分组"
        size="small"
        class="inline-add-btn"
        @click="emit('create-group')"
      >
        <IconifyIconOffline icon="ep:plus" />
      </el-button>
    </div>
  </div>

  <!-- 标签选择 -->
  <div class="mt-3">
    <span class="text-xs mb-1 block" :style="{ color: 'var(--text-secondary)' }"
      >标签（可选）</span
    >
    <div class="flex gap-2">
      <el-select
        ref="tagSelectRef"
        v-model="tagIdsModel"
        multiple
        filterable
        placeholder="选择标签"
        class="flex-1 tag-select"
        size="small"
        filter-placeholder="搜索标签"
        @change="tagChange"
      >
        <el-option
          v-for="tag in tags"
          :key="tag.id"
          :label="tag.name"
          :value="tag.id"
        >
          <div class="flex items-center gap-2">
            <span
              class="w-3 h-3 rounded-full"
              :style="{
                backgroundColor: tag.color || 'var(--text-disabled)'
              }"
            />
            <span>{{ tag.name }}</span>
          </div>
        </el-option>
      </el-select>
      <el-button
        aria-label="新建标签"
        size="small"
        class="inline-add-btn"
        @click="emit('create-tag')"
      >
        <IconifyIconOffline icon="ep:plus" />
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
// 已选资产的「归组编排」区：置顶开关 + 加入分组 + 标签，行内「+」复用全局新建弹窗。
// #980 拆分自 AddToWatchlistModal.vue，受控 v-model，状态留在父层（脏检查要读它）。
// 多根片段：与拆分前 DOM 结构一致，父层不必多包一层 div。
import { computed, nextTick, ref, type ComponentPublicInstance } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import type { WatchlistGroup, WatchlistTag } from "@/api/watchlist";

const props = defineProps<{
  /** 已在自选时隐藏置顶开关（原 v-if="!assetAlreadyExists"） */
  showPin: boolean;
  pinToTop: boolean;
  groupIds: number[];
  tagIds: number[];
  groups: WatchlistGroup[];
  tags: WatchlistTag[];
}>();
const emit = defineEmits<{
  "update:pinToTop": [value: boolean];
  "update:groupIds": [value: number[]];
  "update:tagIds": [value: number[]];
  /** 点行内「+」：打开父层的「新建分组」弹窗 */
  "create-group": [];
  /** 点行内「+」：打开父层的「新建标签」弹窗 */
  "create-tag": [];
}>();

const pinToTopModel = computed({
  get: () => props.pinToTop,
  set: val => emit("update:pinToTop", val)
});
const groupIdsModel = computed({
  get: () => props.groupIds,
  set: val => emit("update:groupIds", val)
});
const tagIdsModel = computed({
  get: () => props.tagIds,
  set: val => emit("update:tagIds", val)
});

const groupSelectRef = ref<ComponentPublicInstance | null>(null);
const tagSelectRef = ref<ComponentPublicInstance | null>(null);

const handleGroupSelect = () => {
  const el = groupSelectRef.value as unknown as {
    query: string;
    visible: boolean;
  } | null;
  if (el) {
    el.query = "";
    el.visible = false;
  }
};

const tagChange = () => {
  const el = tagSelectRef.value as unknown as {
    query: string;
    visible: boolean;
  } | null;
  if (el) el.visible = false;
  nextTick(() => {
    const el2 = tagSelectRef.value as unknown as {
      query: string;
      visible: boolean;
    } | null;
    if (el2) el2.query = "";
  });
};
</script>

<style scoped>
/* 标签选中样式：使用品牌色系统 */
.tag-select :deep(.el-select__tags .el-tag) {
  padding: 0 8px;
  margin: 2px 4px 2px 0;
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-400);
}

/* 行内「新建」入口按钮，与工具栏 icon-tool-btn 视觉一致 */
.inline-add-btn {
  width: 32px;
  height: 32px;
  padding: 0;
  color: var(--text-tertiary-ink);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.inline-add-btn:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}
</style>
