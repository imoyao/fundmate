<template>
  <div class="olf-done">
    <p class="olf-done__title">回填完成</p>
    <p>
      已补全 <strong>{{ result.updated }}</strong> 条流水的账本，日志编号
      <strong>#{{ result.log_id }}</strong>
    </p>
    <ul class="olf-done__ledgers">
      <li v-for="lg in result.ledgers" :key="lg.id">
        账本 #{{ lg.id }}（{{ lg.name || "未命名" }}）：{{ lg.count }} 条
      </li>
    </ul>
    <p>份额与金额未改动：本次只补全流水归属，其它字段保持原值。</p>
    <el-button
      v-if="!undone"
      type="danger"
      plain
      :loading="undoing"
      @click="emit('undo')"
    >
      撤销本次回填
    </el-button>
    <p v-else class="olf-done__undone">本次回填已撤销</p>
  </div>
</template>

<script setup lang="ts">
import type { OrphanLedgerBackfillResult } from "@/api/reconciliation";

/** 回填成功态（#2875）：显式给出 log_id 与逐账本条数，撤销是唯一后续写动作。 */
defineProps<{
  result: OrphanLedgerBackfillResult;
  undone: boolean;
  undoing: boolean;
}>();
const emit = defineEmits<{ undo: [] }>();
</script>

<style scoped>
.olf-done p {
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.olf-done__title {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-success-ink);
}

.olf-done__ledgers {
  padding-left: 18px;
  margin: 6px 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.olf-done__undone {
  font-weight: 600;
  color: var(--color-info-ink);
}
</style>
