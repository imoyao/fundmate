<template>
  <!--
    队列筛选：展示分段走 SegmentedControl（design.md「多选一、选项少一律走此组件」）；
    关键词与导入批次是二级筛选，平铺在同一行，不放左侧栏、不做横向滚动。
    批量选择栏已删除：一键处理是全量动作，不再勾选子集。
  -->
  <div class="recon-filter">
    <div class="recon-filter__row">
      <SegmentedControl
        :model-value="segment"
        :options="options"
        aria-label="按展示分段筛选"
        @update:model-value="emit('update:segment', $event)"
      />
      <el-input
        :model-value="keyword"
        class="recon-filter__search"
        size="small"
        clearable
        placeholder="搜标的代码、账户名或说明"
        aria-label="搜索待办"
        @update:model-value="emit('update:keyword', String($event ?? ''))"
      />
      <el-select
        :model-value="batchId"
        class="recon-filter__batch"
        size="small"
        :disabled="batchOptions.length === 0"
        @update:model-value="emit('update:batchId', $event)"
      >
        <el-option label="来自全部导入" value="all" />
        <el-option
          v-for="option in batchOptions"
          :key="option.id"
          :label="option.label"
          :value="option.id"
        />
      </el-select>
    </div>

    <div class="recon-filter__meta">
      <span>找到 {{ resultCount }} 项待办</span>
      <el-button v-if="dirty" size="small" text @click="emit('reset')">
        清除筛选
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import { DEFAULT_QUEUE_FILTER } from "../utils/reconQueue";
import type { ReconQueueSegment } from "../constants/reconTasks";

defineOptions({ name: "ReconQueueFilter" });

const props = defineProps<{
  segment: ReconQueueSegment;
  options: readonly {
    label: string;
    value: ReconQueueSegment;
    count: number;
  }[];
  keyword: string;
  batchId: number | "all";
  batchOptions: Array<{ id: number; label: string }>;
  resultCount: number;
}>();

const emit = defineEmits<{
  "update:segment": [value: ReconQueueSegment];
  "update:keyword": [value: string];
  "update:batchId": [value: number | "all"];
  reset: [];
}>();

/** 与默认筛选逐项比较：默认档是 `segment: "ready"` */
const dirty = computed(
  () =>
    props.keyword !== DEFAULT_QUEUE_FILTER.keyword ||
    props.segment !== DEFAULT_QUEUE_FILTER.segment ||
    props.batchId !== DEFAULT_QUEUE_FILTER.batchId
);
</script>

<style scoped>
.recon-filter {
  margin-bottom: var(--space-compact);
}

.recon-filter__row,
.recon-filter__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.recon-filter__row {
  margin-bottom: var(--space-2);
}

.recon-filter__search {
  width: min(260px, 100%);
}

.recon-filter__batch {
  width: min(240px, 100%);
}

.recon-filter__meta {
  min-height: 28px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
