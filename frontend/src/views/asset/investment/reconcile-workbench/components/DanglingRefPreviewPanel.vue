<template>
  <div class="dfd-preview">
    <div class="dfd-preview__head">
      <span class="dfd-preview__title">影响预览</span>
      <el-button
        size="small"
        :disabled="!canPreview || previewing"
        :loading="previewing"
        @click="emit('preview')"
      >
        预览影响
      </el-button>
    </div>
    <template v-if="preview">
      <div class="dfd-preview__grid">
        <span
          >当前份额 <strong>{{ preview.quantity_before }}</strong></span
        >
        <span>
          若手动重算的预估份额
          <strong>{{ preview.quantity_if_recomputed }}</strong>
        </span>
        <span
          >差额 <strong>{{ preview.delta }}</strong></span
        >
        <span
          >涉及流水 <strong>{{ preview.txn_count }}</strong> 条</span
        >
      </div>
      <p class="dfd-preview__note">
        本次只回补流水归属，份额不会变动；「若手动重算」仅用于判断后续是否需要手工对齐。
      </p>
      <p v-if="preview.safe" class="dfd-preview__safe is-safe">
        预览判定：数据自洽
      </p>
      <p v-else class="dfd-preview__warn">
        数据不自洽，系统只回补归属、不会改动份额；如需对齐请到持仓页手动重算。
      </p>
      <ul v-if="preview.warnings.length" class="dfd-warnings">
        <li v-for="(w, i) in preview.warnings" :key="i">{{ w }}</li>
      </ul>
    </template>
    <p v-else class="dfd-preview__empty">
      尚未预览。选定目标持仓后点「预览影响」，看过影响才能提交。
    </p>
  </div>
</template>

<script setup lang="ts">
import type { DanglingRefPreview } from "@/api/reconciliation";

/** 影响预览区（#2866）：把 safe / warnings 与四项份额数字摆到提交按钮之前。 */
defineProps<{
  preview: DanglingRefPreview | null;
  previewing: boolean;
  canPreview: boolean;
}>();
const emit = defineEmits<{ preview: [] }>();
</script>

<style scoped>
.dfd-preview {
  padding: 10px 12px;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.dfd-preview__head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.dfd-preview__title {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--color-primary-ink);
}

.dfd-preview__grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.dfd-preview__grid strong {
  font-variant-numeric: tabular-nums;
  color: var(--color-info-ink);
}

.dfd-preview__note {
  margin: 8px 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.dfd-preview__safe {
  margin: 8px 0 0;
  font-size: var(--text-label);
  font-weight: 600;
}

.is-safe {
  color: var(--color-success-ink);
}

.dfd-preview__warn {
  padding: 8px 10px;
  margin: 8px 0 0;
  font-size: var(--text-label);
  font-weight: 600;
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: color-mix(in srgb, var(--color-warning-ink) 10%, transparent);
  border-radius: var(--radius-sm);
}

.dfd-warnings {
  padding-left: 18px;
  margin: 6px 0 0;
  font-size: var(--text-label);
  color: var(--color-warning-ink);
}

.dfd-preview__empty {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}
</style>
