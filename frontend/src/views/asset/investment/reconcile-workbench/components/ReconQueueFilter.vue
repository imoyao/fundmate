<template>
  <!--
    队列筛选：待办状态走 SegmentedControl（design.md「多选一、选项少一律走此组件」）；
    关键词与导入批次是二级筛选，平铺在同一行，不放左侧栏、不做横向滚动。
    批量栏只在真的有可批量项时出现，避免常态占一行空白。
  -->
  <div class="recon-filter">
    <div class="recon-filter__row">
      <SegmentedControl
        :model-value="state"
        :options="options"
        aria-label="按待办状态筛选"
        @update:model-value="emit('update:state', $event)"
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
      <template v-if="taskLabel">
        <span>· 仅看「{{ taskLabel }}」</span>
        <el-button size="small" text @click="emit('clearTask')">
          查看全部任务
        </el-button>
      </template>
      <el-button
        v-if="keyword || state !== 'all' || batchId !== 'all'"
        size="small"
        text
        @click="emit('reset')"
      >
        清除筛选
      </el-button>
    </div>

    <div v-if="selectableCount > 0" class="recon-filter__bulk">
      <el-checkbox
        :model-value="allSelected"
        :indeterminate="selectedCount > 0 && !allSelected"
        @change="emit('toggleAll')"
      >
        选中全部可直接处理的 {{ selectableCount }} 项
      </el-checkbox>
      <span class="recon-filter__bulk-count">
        已选 {{ selectedCount }} 项 · 共 {{ selectedRecords }} 条记录
      </span>
      <el-button
        size="small"
        type="primary"
        :disabled="selectedCount === 0"
        :loading="busy"
        @click="emit('batch')"
      >
        批量回补（{{ selectedCount }}）
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import type { ReconQueueState } from "../constants/reconTasks";

defineOptions({ name: "ReconQueueFilter" });

defineProps<{
  state: ReconQueueState | "all";
  options: readonly {
    label: string;
    value: ReconQueueState | "all";
    count: number;
  }[];
  keyword: string;
  batchId: number | "all";
  batchOptions: Array<{ id: number; label: string }>;
  resultCount: number;
  taskLabel: string | null;
  selectableCount: number;
  selectedCount: number;
  selectedRecords: number;
  allSelected: boolean;
  busy: boolean;
}>();

const emit = defineEmits<{
  "update:state": [value: ReconQueueState | "all"];
  "update:keyword": [value: string];
  "update:batchId": [value: number | "all"];
  toggleAll: [];
  batch: [];
  clearTask: [];
  reset: [];
}>();
</script>

<style scoped>
.recon-filter {
  margin-bottom: var(--space-compact);
}

.recon-filter__row,
.recon-filter__meta,
.recon-filter__bulk {
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

.recon-filter__bulk {
  padding: 8px 12px;
  margin-top: var(--space-2);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.recon-filter__bulk-count {
  flex: 1 1 auto;
  font-size: var(--text-label);
  color: var(--text-secondary);
}
</style>
