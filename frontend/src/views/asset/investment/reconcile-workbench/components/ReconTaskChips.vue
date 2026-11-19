<template>
  <!--
    judge 段内的类型 chips：把「要你判断」再按三类财务动作细分。
    语义是筛选不是导航（与已删的 WorkbenchTaskCards 同一职责，降级为一行 chips）。
  -->
  <div class="recon-task-chip-group" role="group" aria-label="按要判断的类型筛选">
    <button
      v-for="task in RECON_TASKS"
      :key="task.key"
      type="button"
      class="recon-task-chip"
      :class="{ 'is-active': active === task.key }"
      :aria-pressed="active === task.key"
      @click="emit('select', task.key)"
    >
      <span>{{ task.label }}</span>
      <span v-if="counts[task.key] > 0" class="recon-task-chip__count">
        {{ counts[task.key] }}
      </span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { RECON_TASKS, type ReconTaskKey } from "../constants/reconTasks";

defineOptions({ name: "ReconTaskChips" });

defineProps<{
  /** 当前选中的任务；`all` 表示未筛选 */
  active: ReconTaskKey | "all";
  /** 三类任务在 judge 段里的件数（与队列条数同源） */
  counts: Record<ReconTaskKey, number>;
}>();

const emit = defineEmits<{ select: [key: ReconTaskKey] }>();
</script>

<style scoped>
.recon-task-chip-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-compact);
}

.recon-task-chip {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 4px 12px;
  font-family: var(--font-ui);
  font-size: var(--text-label);
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.recon-task-chip:hover {
  border-color: var(--border-default);
}

.recon-task-chip:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.recon-task-chip.is-active {
  color: var(--brand-ink);
  background: var(--brand-100);
  border-color: var(--brand-300);
}

.recon-task-chip__count {
  min-width: 18px;
  padding: 0 5px;
  font-variant-numeric: tabular-nums;
  text-align: center;
  color: var(--text-inverse);
  background: var(--brand-solid);
  border-radius: var(--radius-pill);
}
</style>
