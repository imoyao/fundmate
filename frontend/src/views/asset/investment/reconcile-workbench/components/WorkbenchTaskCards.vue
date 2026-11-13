<template>
  <!--
    四张任务分诊卡（design.md「导入预览问题摘要三卡片」形态；2026-11-13 起
    待重建持仓自成一卡，共四张）。

    ⚠️ 这不是 tab：卡是数据摘要 + 过滤器，点它只过滤下方队列、不切换视图。
    语义用 role="button" + aria-pressed（沿用姐妹页 CategoryTabs.vue），
    不手写分组导航的 ARIA 角色——那是 SegmentedControl 的职责，手写会被
    scripts/guard_segmented.py 拦下。
  -->
  <div class="workbench-tabs" aria-label="按要处理的事情筛选">
    <div
      v-for="task in RECON_TASKS"
      :key="task.key"
      class="recon-task-card"
      :class="[
        `recon-task-card--${task.tone}`,
        { 'is-active': active === task.key }
      ]"
      role="button"
      tabindex="0"
      :aria-pressed="active === task.key"
      :aria-label="`${task.label}，${counts[task.key]} 项待办`"
      @click="emit('select', task.key)"
      @keydown.enter.prevent="emit('select', task.key)"
      @keydown.space.prevent="emit('select', task.key)"
    >
      <div class="recon-task-card__head">
        <span class="recon-task-card__label">{{ task.label }}</span>
        <span v-if="counts[task.key] > 0" class="domain-tab-count">
          {{ counts[task.key] }}
        </span>
      </div>
      <p class="recon-task-card__hint">{{ task.hint }}</p>
      <div class="recon-task-card__foot">
        <span v-if="counts[task.key] === 0" class="recon-task-card__none">
          暂无待办
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { RECON_TASKS, type ReconTaskKey } from "../constants/reconTasks";

defineOptions({ name: "WorkbenchTaskCards" });

defineProps<{
  /** 当前选中的任务；`all` 表示未筛选 */
  active: ReconTaskKey | "all";
  /** 四类任务的待办件数（与队列条数同源，见 utils/reconQueue.ts） */
  counts: Record<ReconTaskKey, number>;
}>();

const emit = defineEmits<{ select: [key: ReconTaskKey] }>();
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* 确定性栅格 + 断点单一来源（_breakpoints.scss）：任何宽度都不出现 3+1 孤行
   （旧 auto-fit 在 4 卡、容器约 964–1168px 时会把第 4 张甩到第二行左侧） */
.workbench-tabs {
  display: grid;
  grid-template-columns: 1fr; /* 默认单列（手机） */
  gap: var(--space-3);
  margin-bottom: var(--space-standard);
}

/* ≥640px：两列两行 */
@include bp.above("sm") {
  .workbench-tabs {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* ≥1024px：一行四张（桌面工作台常态） */
@include bp.above("lg") {
  .workbench-tabs {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.recon-task-card {
  min-height: 118px;
  padding: var(--space-compact) var(--space-standard);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.recon-task-card:hover {
  background: var(--bg-hover);
}

.recon-task-card:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.recon-task-card.is-active {
  background: var(--brand-100);
  border-color: var(--brand-300);
}

.recon-task-card__head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.recon-task-card__label {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.recon-task-card--info .recon-task-card__label {
  color: var(--color-info-ink);
}

.recon-task-card--warning .recon-task-card__label {
  color: var(--color-warning-ink);
}

.recon-task-card--brand .recon-task-card__label {
  color: var(--brand-ink);
}

.domain-tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  line-height: 1;
  color: var(--text-inverse);
  background: var(--brand-solid);
  border-radius: var(--radius-pill);
}

.recon-task-card__hint {
  margin: 8px 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

.recon-task-card__foot {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: baseline;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.recon-task-card__none {
  color: var(--text-tertiary-ink);
}
</style>
