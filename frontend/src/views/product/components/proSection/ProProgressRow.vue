<script setup lang="ts">
import { computed } from "vue";
import type { ProStatusResult } from "@/api/products";
import { progressText } from "./proModel";

/**
 * 已开通态的「模块进度」行（#2523）。
 *
 * 四张介绍卡换成一行的理由：介绍卡是获客件，付费用户看进度不看推销；
 * 但「哪些上线 / 哪个在建」的状态位信号不能丢（与徽标同源，来自后端
 * `modules[*].phase`）。全上线时只有计数，不硬凑「建设中」。
 */
const props = defineProps<{
  status: ProStatusResult | null;
}>();

const text = computed(() => progressText(props.status));
</script>

<template>
  <div class="pro-section__progress">
    <span class="pro-section__progress-label">模块进度</span>
    <span class="pro-section__progress-text">{{ text }}</span>
  </div>
</template>

<style scoped>
/* 已开通态模块进度行（#2523）：一行代替四张介绍卡。标签用品牌文字级、
   数值用主文字级——「模块进度」是语境不是数据，数据是后面的计数与 Phase。 */
.pro-section__progress {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
  padding: var(--space-3);
  background: var(--bg-muted);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.pro-section__progress-label {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--brand-ink);
}

.pro-section__progress-text {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}
</style>
