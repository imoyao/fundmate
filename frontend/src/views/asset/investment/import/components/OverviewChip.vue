<script setup lang="ts">
/**
 * 概览条上的一颗类别胶囊（从 SummaryPanel 拆出，2026-11-02）。
 *
 * 拆出理由：一颗胶囊里有**两个互相独立的动作靶区**——左侧复选框按类全选、
 * 右侧主体筛选表格。两者语义不同（勾选 ≠ 筛选），但旧版把它们连同样式一起
 * 挤在概览条里，读模板时容易误以为「点胶囊 = 勾选」。独立成一个组件后，
 * 「两个靶区」这件事在结构上可见，而不再是缩进里的约定。
 *
 * 注意：根元素**必须单根**。`data-category`（e2e 与筛选逻辑共用）挂在根上，
 * Vue 的 attribute fallthrough 对多根组件失效且只告警不报错 —— 一旦改成多根，
 * `.ov-chip[data-category="fix"]` 会静默匹配不到，用例转红前先看到的是「找不到元素」。
 */
import type { SummaryCategory } from "../composables/useImportWizard";

defineProps<{
  category: SummaryCategory;
  label: string;
  /** 语义色：绿=可导入 / 橙=可导入但需留意 / 红=阻断（与状态列三态同源） */
  tone: "success" | "warning" | "danger";
  /** 悬停说明：胶囊只有 4 个字，语义靠它补 */
  hint: string;
  count: number;
  /** 表格当前是否正被这个类别筛选 */
  active: boolean;
  /** 该类别勾选态（与 el-checkbox 的 model/indeterminate 一一对应） */
  checkState: "all" | "some" | "none";
}>();

const emit = defineEmits<{
  (e: "check", value: boolean): void;
  (e: "toggle"): void;
}>();
</script>

<template>
  <div
    class="ov-chip"
    :class="[`ov-chip--${tone}`, { 'is-active': active }]"
    :data-category="category"
    :title="hint"
  >
    <el-checkbox
      class="ov-chip-check"
      :model-value="checkState === 'all'"
      :indeterminate="checkState === 'some'"
      :aria-label="`${label}全选`"
      @change="emit('check', Boolean($event))"
    />
    <button
      type="button"
      class="ov-chip-btn"
      :aria-pressed="active"
      @click="emit('toggle')"
    >
      <span class="ov-dot" aria-hidden="true" />
      <span class="ov-label">{{ label }}</span>
      <strong class="ov-count">{{ count }}</strong>
    </button>
  </div>
</template>

<style scoped>
/* ── 胶囊：外层只管边框与选中态，内层是两个独立靶区 ── */
.ov-chip {
  display: inline-flex;
  gap: 2px;
  align-items: center;
  height: 30px;
  padding: 0 10px 0 8px;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: 999px;
  transition:
    border-color 0.15s,
    background 0.15s;
}

.ov-chip:hover {
  border-color: var(--color-primary-20);
}

/* 选中 = 表格正被这个类别筛选，用主色描边而非填充，避免与语义色点抢注意力 */
.ov-chip.is-active {
  background: var(--color-primary-10);
  border-color: var(--color-primary);
}

.ov-chip :deep(.el-checkbox) {
  height: auto;
  margin-right: 0;
}

.ov-chip-btn {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 100%;
  padding: 0 2px;
  font-family: inherit;
  font-size: var(--text-label);
  color: var(--text-primary);
  cursor: pointer;
  background: none;
  border: 0;
}

.ov-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* 语义色与状态列三态同源：绿=可导入 / 橙=可导入但需留意 / 红=阻断 */
.ov-chip--success .ov-dot {
  background: var(--color-success-ink);
}

.ov-chip--warning .ov-dot {
  background: var(--color-warning-ink);
}

.ov-chip--danger .ov-dot {
  background: var(--color-danger-ink);
}

.ov-label {
  white-space: nowrap;
}

.ov-count {
  font-size: var(--text-small);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}
</style>
