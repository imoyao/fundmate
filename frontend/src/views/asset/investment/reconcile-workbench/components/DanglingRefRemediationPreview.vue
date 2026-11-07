<template>
  <div v-if="mode === 'enrich'">
    <div v-if="enrichPreview" class="dr-panel">
      <p class="dr-stats">
        涉及 {{ enrichPreview.txn_count }} 条 · 将补标的代码
        {{ enrichPreview.fill_symbol_count }} 条 · 将补交易日期
        {{ enrichPreview.fill_date_count }} 条 · 无需改动
        {{ enrichPreview.unchanged_count }} 条
      </p>
      <p class="dr-sub">
        候选持仓（{{ enrichPreview.candidate_positions.length }}）
      </p>
      <ul v-if="candidateLines.length" class="dr-list">
        <li v-for="(line, i) in candidateLines" :key="i">{{ line }}</li>
      </ul>
      <p v-else class="dr-muted">
        暂无同标的现存持仓，补全信息后仍需补建持仓或补录流水。
      </p>
      <p class="dr-sub">前 8 条变更</p>
      <ul class="dr-list">
        <li v-for="(line, i) in enrichChangeLines" :key="i">{{ line }}</li>
      </ul>
      <ul v-if="enrichPreview.warnings.length" class="dr-warnings">
        <li v-for="(w, i) in firstWarnings(enrichPreview.warnings)" :key="i">
          {{ w }}
        </li>
      </ul>
    </div>
  </div>
  <template v-else>
    <div v-if="deletePreview" class="dr-panel">
      <p class="dr-stats">
        将删除 {{ deletePreview.txn_count }} 条 · 金额合计
        {{ deletePreview.total_amount }} 元 · 完整快照
        {{ deletePreview.snapshot_columns }} 列
      </p>
      <ul v-if="deletePreview.warnings.length" class="dr-warnings">
        <li v-for="(w, i) in firstWarnings(deletePreview.warnings)" :key="i">
          {{ w }}
        </li>
      </ul>
      <p class="dr-sub">前 8 条明细</p>
      <ul class="dr-list">
        <li v-for="(line, i) in deleteDetailLines" :key="i">{{ line }}</li>
      </ul>
    </div>
    <p v-else-if="previewing" class="dr-muted">正在查看影响…</p>
    <p v-else class="dr-muted">尚未取得影响预览。</p>
  </template>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type {
  DanglingRefDeletePreview,
  DanglingRefEnrichPreview
} from "@/api/reconciliation";

/** 「补全信息 / 删除」的影响预览面板（#2866 后续）：纯展示，不含任何写动作。
 *  从主弹窗拆出，避免单文件超过 check_vue_size.mjs 的 400 行阈值。 */
const props = defineProps<{
  mode: "enrich" | "delete";
  enrichPreview: DanglingRefEnrichPreview | null;
  deletePreview: DanglingRefDeletePreview | null;
  previewing: boolean;
}>();

const candidateLines = computed(() =>
  (props.enrichPreview?.candidate_positions ?? []).map(
    c => `#${c.id} ${c.symbol} · ${c.quantity} 份 · ${c.ownership_status}`
  )
);
const enrichChangeLines = computed(() =>
  (props.enrichPreview?.changes ?? [])
    .slice(0, 8)
    .map(
      ch =>
        `#${ch.id} 标的 ${ch.symbol_before || "缺"} → ${ch.symbol_after || "缺"} · 日期 ${ch.trade_date_before || "缺"} → ${ch.trade_date_after || "缺"}`
    )
);
const deleteDetailLines = computed(() =>
  (props.deletePreview?.transactions ?? [])
    .slice(0, 8)
    .map(
      t =>
        `#${t.id} ${t.txn_type} · ${t.trade_date || "缺交易日期"} · ${t.symbol || "缺标的代码"} · ${t.quantity} 份 / ${t.amount} 元`
    )
);
/** 后端 warnings 有 3~4 条，面板只铺前 3 条，避免长文案把弹窗撑满。 */
function firstWarnings(list: string[]): string[] {
  return list.slice(0, 3);
}
</script>

<style scoped>
.dr-panel {
  padding: 10px 12px;
  margin-bottom: 10px;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.dr-stats,
.dr-muted,
.dr-list,
.dr-warnings {
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-tertiary-ink);
}

.dr-stats {
  line-height: 1.7;
}

.dr-muted {
  margin: 4px 0;
}

.dr-sub {
  margin: 10px 0 4px;
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--color-primary-ink);
}

.dr-list,
.dr-warnings {
  padding-left: 18px;
  margin: 0;
}

.dr-warnings {
  margin-top: 8px;
  color: var(--color-warning-ink);
}
</style>
