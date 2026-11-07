<template>
  <!--
    三张任务分诊卡（design.md「导入预览问题摘要三卡片」形态）。

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
        <span class="recon-task-card__number">{{ counts[task.key] }}</span>
        <span>项待办</span>
        <span v-if="readyCounts[task.key] > 0" class="recon-task-card__ready">
          · 其中 {{ readyCounts[task.key] }} 项可直接处理
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
  /** 三类任务的待办记录条数（与状态计数同源，见 utils/reconQueue.ts） */
  counts: Record<ReconTaskKey, number>;
  /** 其中「可直接处理」的项数 */
  readyCounts: Record<ReconTaskKey, number>;
}>();

const emit = defineEmits<{ select: [key: ReconTaskKey] }>();
</script>

<style scoped>
.workbench-tabs {
  display: grid;

  /* auto-fit 让窄屏自动收成单列，无需裸像素媒体查询（guard_breakpoints.py） */
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3);
  margin-bottom: var(--space-standard);
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

.recon-task-card__number {
  font-family: var(--font-mono);
  font-size: var(--text-num-strong);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.recon-task-card__ready {
  color: var(--color-success-ink);
}
</style>
