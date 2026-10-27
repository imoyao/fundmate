<template>
  <!-- Tab 标签：域名 + 待处理数角标（#1259）。
       角标仅在 pending > 0 时出现——0 项时保持纯文字，避免每个 tab 尾巴上
       挂一个灰色的 "0"，把「有待办」这个信号稀释掉。 -->
  <span class="domain-tab-label">
    {{ label }}
    <span v-if="count > 0" class="domain-tab-count">{{ count }}</span>
  </span>
</template>

<script setup lang="ts">
/**
 * 对账工作台域 Tab 的标签（#980 批 B3 拆分自 reconcile-workbench/index.vue，
 * 零视觉/行为变更）：`<template #label>` 槽内的「域名 + 待处理数角标」。
 */
defineProps<{
  /** 域名（全部 / 持仓快照 / 对账单 …） */
  label: string;
  /** 该域待处理差异数（> 0 才渲染角标） */
  count: number;
}>();
</script>

<style scoped>
/* Tab 标签内的各域待处理数角标（#1259） */
.domain-tab-label {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.domain-tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  font-size: var(--text-label);
  line-height: 1;
  color: var(--text-inverse);
  background: var(--brand-600, #d98b2b);
  border-radius: 999px;
}
</style>
