<script setup lang="ts">
/**
 * 表格空状态（迁移自 reconcile/reconcileView/ReconcileEmpty.vue）。
 *
 * 鹦鹉螺插画资产未入库前先用文案版 + 品牌收尾文案（与 watchlist 空状态同一策略）。
 * 文案分「全量无记录」与「当前筛选无记录」两种——后者要多给一句出路，
 * 否则用户只会以为数据没了。
 */
import { IconifyIconOffline } from "@/components/ReIcon";
import { STATUS_ALL } from "./model";

defineProps<{ statusFilter: string }>();
</script>

<template>
  <div class="reconcile-empty">
    <IconifyIconOffline icon="ep:files" class="reconcile-empty__icon" />
    <p class="reconcile-empty__title">
      {{ statusFilter === STATUS_ALL ? "暂无对账记录" : "当前筛选下没有记录" }}
    </p>
    <p class="reconcile-empty__copy">潮有涨落，壳有深浅。算得清，才无患。</p>
    <p v-if="statusFilter !== STATUS_ALL" class="reconcile-empty__hint">
      试试切换其他状态，或点右上角刷新
    </p>
  </div>
</template>

<style scoped>
/* ===== 空状态（鹦鹉螺插画资产到位前文案版） ===== */
.reconcile-empty {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  padding: 40px 0;
}

.reconcile-empty__icon {
  margin-bottom: 6px;
  font-size: var(--text-display-lg);
  color: var(--text-tertiary);
  opacity: 0.4;
}

.reconcile-empty__title {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-secondary);
}

.reconcile-empty__copy {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.reconcile-empty__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
