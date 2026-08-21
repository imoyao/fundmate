<script setup lang="ts">
/* eslint-disable vue/no-mutating-props -- 状态注入模式：groups/tags/toolbar 为 composable 实例 prop，
   经 computed get/set 桥接修改其内部 ref 属有意设计（与 WatchlistToolbar 同模式） */
import { computed } from "vue";
import { ElTag } from "element-plus";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { WatchlistToolbarState } from "@/composables/useWatchlistData";

/**
 * 自选筛选条（分组 Tab + 标签筛选面板 + 视图 Segmented），从 index.vue 顶部区块抽出（2026-08-20）。
 * 纯展示 + 事件转发：状态全部在 groups / tags / toolbar 三个 composable，本组件不持有业务状态。
 */
const props = defineProps<{
  groups: ReturnType<typeof useWatchlistGroups>;
  tags: ReturnType<typeof useWatchlistTags>;
  toolbar: WatchlistToolbarState;
}>();

const emit = defineEmits<{
  (e: "view-change"): void;
  (e: "tag-apply"): void;
  (e: "tag-clear"): void;
}>();

// 状态注入模式：groups / tags / toolbar 为 composable 实例 prop，
// 双向绑定经 computed get/set 桥接其内部 ref（避免 vue/no-mutating-props）
const activeGroupModel = computed({
  get: () => props.groups.activeGroup.value,
  set: (value: string) => {
    props.groups.activeGroup.value = value;
  }
});
const allGroups = computed(() => props.groups.allGroups.value);
const tagFilterVisibleModel = computed({
  get: () => props.tags.tagFilterVisible.value,
  set: (value: boolean) => {
    props.tags.tagFilterVisible.value = value;
  }
});
const draftFilterTagIdsModel = computed({
  get: () => props.tags.draftFilterTagIds.value,
  set: (value: number[]) => {
    props.tags.draftFilterTagIds.value = value;
  }
});
const allTags = computed(() => props.tags.allTags.value);
const currentViewModel = computed({
  get: () => props.toolbar.currentView.value,
  set: (value: "all" | "exchange" | "otc") => {
    props.toolbar.currentView.value = value;
  }
});
const selectedTagCount = computed(
  () => props.tags.selectedFilterTagIds.value.length
);
</script>

<template>
  <div class="filter-bar">
    <div class="flex items-center gap-2 flex-wrap">
      <!-- 分组 Tab -->
      <el-tabs v-model="activeGroupModel" class="watchlist-tabs">
        <el-tab-pane v-for="g in allGroups" :key="g.key" :name="g.key">
          <template #label>
            <span class="tab-label">
              <span>{{ g.label }}</span>
              <el-tag
                v-if="g.count > 0"
                size="small"
                effect="plain"
                round
                :style="{
                  marginLeft: '4px',
                  color: g.color || 'var(--text-secondary)',
                  borderColor: g.color || 'var(--border-color)'
                }"
              >
                {{ g.count }}
              </el-tag>
            </span>
          </template>
        </el-tab-pane>
      </el-tabs>

      <!-- 标签筛选 -->
      <el-popover
        :visible="tagFilterVisibleModel"
        placement="bottom"
        :width="260"
        title="按标签筛选"
      >
        <template #reference>
          <el-button
            plain
            size="small"
            @click="
              tags.onTagFilterShow();
              tagFilterVisibleModel = true;
            "
          >
            标签筛选<template v-if="selectedTagCount">
              ({{ selectedTagCount }})
            </template>
          </el-button>
        </template>
        <div class="tag-filter-panel">
          <el-checkbox-group v-model="draftFilterTagIdsModel">
            <el-checkbox
              v-for="t in allTags"
              :key="t.id"
              :value="t.id"
              :label="t.name"
            >
              {{ t.name }}
            </el-checkbox>
          </el-checkbox-group>
          <div class="flex justify-end gap-2 mt-3">
            <el-button size="small" @click="tagFilterVisibleModel = false">
              取消
            </el-button>
            <el-button size="small" type="primary" @click="emit('tag-apply')">
              确定
            </el-button>
          </div>
        </div>
      </el-popover>

      <!-- 视图 segmented：全部 / 场内 / 场外（唯一 venue 入口） -->
      <el-segmented
        v-model="currentViewModel"
        size="small"
        :options="[
          { label: '全部', value: 'all' },
          { label: '场内', value: 'exchange' },
          { label: '场外', value: 'otc' }
        ]"
        @change="emit('view-change')"
      />
    </div>
  </div>
</template>

<style scoped>
.filter-bar {
  margin-bottom: 12px;
}

.tab-label {
  display: inline-flex;
  align-items: center;
}

.tag-filter-panel {
  max-height: 240px;
  overflow-y: auto;
}
</style>
