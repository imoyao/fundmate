<script setup lang="ts">
import { HIGH_THRESHOLD, DASH } from "./allocModel";

/**
 * 无 peer 时的引导（#980 拆分）。
 *
 * 这不是错误态：把「为什么没内容」讲清楚，比一句「暂无数据」有用得多。
 * `reason` 来自后端（如「家庭持仓不足 2 只」），有就接着说，没有就退回「—」。
 */
defineProps<{
  reason?: string | null;
}>();
</script>

<template>
  <div class="pro-alloc__empty">
    <p class="pro-alloc__empty-title">这里将展示「你是否真的分散了」</p>
    <p class="pro-alloc__empty-desc">
      买入这只标的后，会逐只计算它与你其余持仓的日收益相关系数：<br />
      相关系数 ≥ {{ HIGH_THRESHOLD }} 说明账面分散、风险仍集中。{{
        reason ? `当前：${reason}` : DASH
      }}
    </p>
  </div>
</template>

<style scoped>
.pro-alloc__empty {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.pro-alloc__empty-title {
  margin: 0;
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.pro-alloc__empty-desc {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}
</style>
