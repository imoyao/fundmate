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
        <span v-if="counts[task.key] === 0" class="recon-task-card__none">
          暂无待办
        </span>
        <template v-else>
          <!-- 角标已给总数，这里只把「能一键处理 / 得逐条判断」拆开说清，
               避免用户拿脚注数字和角标对不上（第三轮反馈）。 -->
          <span v-if="readyCounts[task.key] > 0" class="recon-task-card__ready">
            {{ readyCounts[task.key] }} 件可一键处理
          </span>
          <span
            v-if="manualCount(task.key) > 0"
            class="recon-task-card__manual"
          >
            {{ readyCounts[task.key] > 0 ? "· 另有 " : ""
            }}{{ manualCount(task.key) }} 件需你逐条判断
          </span>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { RECON_TASKS, type ReconTaskKey } from "../constants/reconTasks";

defineOptions({ name: "WorkbenchTaskCards" });

const props = defineProps<{
  /** 当前选中的任务；`all` 表示未筛选 */
  active: ReconTaskKey | "all";
  /** 三类任务的待办件数（与队列条数同源，见 utils/reconQueue.ts） */
  counts: Record<ReconTaskKey, number>;
  /** 其中「可直接处理（可一键处理）」的件数 */
  readyCounts: Record<ReconTaskKey, number>;
}>();

const emit = defineEmits<{ select: [key: ReconTaskKey] }>();

/** 待办件数减去可一键处理的，即为需要人工逐一判断的件数。
 *  把「可自动 / 需人工」拆开说明，避免角标总数与下方口径让用户对不上。 */
function manualCount(key: ReconTaskKey): number {
  return Math.max(0, props.counts[key] - props.readyCounts[key]);
}
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

.recon-task-card__ready {
  color: var(--color-success-ink);
}

.recon-task-card__manual {
  color: var(--color-warning-ink);
}

.recon-task-card__none {
  color: var(--text-tertiary-ink);
}
</style>
