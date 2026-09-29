<!--
  RoadFilterBar · 两级筛选（design.md「Filter & Selection」硬规范）

  - 一级（主维度）：全部 / 股票 / 基金 / 经理 / 指数 → **`SegmentedControl`**（#1731 收敛，
    逐项数量走 `count` 徽章）。它属「多选一、选项少」的分段控制器语义，不是筛选胶囊栏。
  - 二级（子维度）：全部状态 / 待复盘 / 持仓中 / 观察中 / 已清仓——**水平滑动胶囊栏**
    （design.md 的二级筛选语言，本组件保留手写），超宽横向滚动不换行（严禁塞进左侧边栏）
  - 右侧工具：搜索、排序、管理模式、设计预览开关

  语言边界见 `components/SegmentedControl/index.vue` 头注释与
  `docs/design/components.md`「分段控制器 vs 相邻「多选一」语言」。
-->
<template>
  <div class="road-filter">
    <div class="road-filter__row">
      <!-- 一级筛选（主维度）→ SegmentedControl（#1731 收敛）。
           原手写 `.road-pills--primary` / `.road-pill` 的注释自称「分段控制器式胶囊，实心选中态」，
           但实现其实是软按钮（--brand-100 底 + --brand-700 字 + --brand-400 边框）——注释与实现不符；
           且它本就是 design.md「Filter & Selection」点名要交给 SegmentedControl 的一级筛选。
           逐项数量改走 `count` 徽章，UX 1:1 保留。 -->
      <SegmentedControl
        :model-value="entityFilter"
        :options="entityOptions"
        aria-label="标的类别筛选"
        @change="onEntityFilterChange"
      />

      <div class="road-filter__tools">
        <el-input
          :model-value="keyword"
          size="small"
          clearable
          placeholder="搜名称或代码"
          class="road-filter__search"
          @update:model-value="$emit('update:keyword', String($event ?? ''))"
        />
        <el-select
          :model-value="sortBy"
          size="small"
          class="road-filter__sort"
          @update:model-value="$emit('update:sortBy', String($event))"
        >
          <el-option
            v-for="option in SORT_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-button
          size="small"
          :type="manageMode ? 'primary' : 'default'"
          @click="$emit('toggle-manage')"
          >{{ manageMode ? "退出管理" : "管理" }}</el-button
        >
        <el-switch
          v-if="devMode"
          :model-value="previewMode"
          size="small"
          inline-prompt
          active-text="示例"
          inactive-text="示例"
          title="设计预览：追加示例卡（基金经理等后端未落地的能力）"
          @update:model-value="$emit('update:previewMode', Boolean($event))"
        />
      </div>
    </div>

    <div class="road-filter__row road-filter__row--sub">
      <div class="road-pills road-pills--scroll" role="tablist">
        <button
          v-for="tab in STATUS_TABS"
          :key="tab.key"
          type="button"
          role="tab"
          class="road-pill road-pill--soft"
          :class="{ 'is-active': statusFilter === tab.key }"
          :aria-selected="statusFilter === tab.key"
          @click="$emit('update:statusFilter', tab.key)"
        >
          {{ tab.label }}
          <span class="road-pill__count">{{ statusCounts[tab.key] ?? 0 }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import { ENTITY_TABS, SORT_OPTIONS, STATUS_TABS } from "../constants";
import type { RoadEntityType, RoadStatusFilter } from "@/types/favorites";

// 示例预览开关仅开发模式可见（生产构建 import.meta.env.DEV 为 false 时隐藏）
const devMode = import.meta.env.DEV;

const props = defineProps<{
  entityFilter: RoadEntityType | "all";
  statusFilter: RoadStatusFilter;
  entityCounts: Record<string, number>;
  statusCounts: Record<string, number>;
  keyword: string;
  sortBy: string;
  manageMode: boolean;
  previewMode: boolean;
}>();

const emit = defineEmits<{
  (e: "update:entityFilter", value: RoadEntityType | "all"): void;
  (e: "update:statusFilter", value: RoadStatusFilter): void;
  (e: "update:keyword", value: string): void;
  (e: "update:sortBy", value: string): void;
  (e: "update:previewMode", value: boolean): void;
  (e: "toggle-manage"): void;
}>();

/**
 * 一级筛选选项（#1731 收敛）：把逐项数量拼成 `SegmentedControl` 的 `count` 徽章，
 * 迁移前后 UX 1:1。`?? 0` 与原模板逐字一致——计数缺失时显示 0，而非隐藏徽章。
 */
const entityOptions = computed(() =>
  ENTITY_TABS.map(tab => ({
    label: tab.label,
    value: tab.key,
    count: props.entityCounts[tab.key] ?? 0
  }))
);

/** 一级筛选变更：`SegmentedControl` 的 `change` 只回传值，转成原有的 update: 事件语义 */
function onEntityFilterChange(value: RoadEntityType | "all") {
  emit("update:entityFilter", value);
}
</script>

<style scoped>
.road-filter {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 20px;
}

.road-filter__row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.road-filter__tools {
  display: flex;
  gap: 8px;
  align-items: center;
}

.road-filter__search {
  width: 168px;
}

.road-filter__sort {
  width: 104px;
}

/* 二级筛选胶囊（水平滑动栏，design.md「Filter & Selection」）：
   一级筛选已迁到 SegmentedControl（#1731），下面这套只服务 `.road-pills--scroll`。 */
.road-pills {
  display: flex;
  gap: 6px;
  align-items: center;
}

.road-pills--scroll {
  flex-wrap: nowrap;
  padding-bottom: 2px;
  overflow-x: auto;
  scrollbar-width: thin;
}

.road-pill {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  transition:
    background-color 0.15s ease,
    color 0.15s ease,
    border-color 0.15s ease;
}

.road-pill:hover {
  background: var(--bg-hover);
}

.road-pill.is-active {
  color: var(--brand-700);
  background: var(--brand-100);
  border-color: var(--brand-400);
}

.road-pill--soft {
  height: 28px;
  padding: 0 12px;
  font-size: 12px;
  background: var(--bg-soft);
}

.road-pill--soft.is-active {
  background: var(--brand-100);
}

.road-pill__count {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.road-pill.is-active .road-pill__count {
  color: var(--brand-700);
}
</style>
