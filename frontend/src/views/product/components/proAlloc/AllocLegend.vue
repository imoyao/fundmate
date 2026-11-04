<script setup lang="ts">
import { LEGEND } from "./allocModel";

/**
 * 相关性档位图例（#980 拆分）。
 *
 * 原实现把定性文案（明显联动 / 反向对冲…）重复写进每一行，行内只剩数字与样本数。
 * 收敛到图例后，行里读「数值」，图例里读「含义」，两处都不挤。
 */
</script>

<template>
  <ul class="pro-alloc__legend" aria-label="相关性档位图例">
    <li v-for="item in LEGEND" :key="item.tier" class="pro-alloc__legend-item">
      <span
        class="pro-alloc__legend-dot"
        :class="`pro-alloc__legend-dot--${item.tier}`"
      />
      {{ item.text }}
    </li>
    <li class="pro-alloc__legend-note">虚线 = 0 轴 · 轨道全程 ρ ∈ [−1, +1]</li>
  </ul>
</template>

<style scoped>
/* ===== 图例（#2400）：每行重复的定性文案收敛到此 ===== */
.pro-alloc__legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-3);
  align-items: center;
  padding: 0;
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
  list-style: none;
}

.pro-alloc__legend-item {
  display: inline-flex;
  gap: var(--space-1);
  align-items: center;
}

.pro-alloc__legend-dot {
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  background: var(--border-default);
  border-radius: var(--radius-xs);
}

.pro-alloc__legend-dot--danger {
  background: var(--color-danger);
}

.pro-alloc__legend-dot--warn {
  background: var(--color-warning-fill);
}

.pro-alloc__legend-dot--hedge {
  background: var(--color-info);
}

.pro-alloc__legend-note {
  color: var(--text-tertiary-ink);
}
</style>
