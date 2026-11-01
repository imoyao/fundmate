<script setup lang="ts">
/**
 * 迁移占位备注的展示（#2749 关联糙边修复）。
 *
 * 历史数据里 `货基持仓迁移为孤儿流水（L3，2026-08-14）` 这种备注对用户是天书——
 * `L3` 是内部迁移批次、括号里是锚定日。这里把「人话」正文正常显示，把内部标记收进一枚
 * 安静的「迁移占位」徽标：正文保持可读，批次/日期只在悬浮 tooltip 里露出来（可追溯但不扰民）。
 *
 * 传入的是**已解析**的结果（`model.parseMigrationNote`）而不是原始字符串：
 * 调用方本来就要先解析一次才知道「是不是迁移备注」，再解析一遍是白费。
 * notes 字段**从不改写**——存储层不动，只在展示层转译。
 */
import { computed } from "vue";
import type { MigrationNote } from "./model";

const props = defineProps<{ note: MigrationNote }>();

const title = computed(() => {
  const parts = ["系统迁移产生的占位记录"];
  if (props.note.batchDate) parts.push(props.note.batchDate);
  if (props.note.batchLevel) parts.push(`批次 ${props.note.batchLevel}`);
  return parts.join(" · ");
});
</script>

<template>
  <span class="migration-note">
    <span class="migration-note__badge" :title="title">迁移占位</span>
    <span class="migration-note__text">{{ note.displayText }}</span>
  </span>
</template>

<style scoped>
.migration-note {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  min-width: 0;
}

/* 安静的胶囊：软底 + 次要字色 + 细描边，不当成警告，也不抢金额注意力 */
.migration-note__badge {
  flex: 0 0 auto;
  padding: 0 6px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xs);
}

.migration-note__text {
  min-width: 0;
  color: var(--text-secondary);
  overflow-wrap: anywhere;
}
</style>
