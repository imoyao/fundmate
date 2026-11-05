<template>
  <div class="dfd-done">
    <p class="dfd-done__title">回补完成</p>
    <p>
      已回补 <strong>{{ result.updated }}</strong> 条流水，日志编号
      <strong>#{{ result.log_id }}</strong>
    </p>
    <p>份额未改动：本次只回补流水归属，持仓份额保持原值。</p>
    <el-button
      v-if="!undone"
      type="danger"
      plain
      :loading="undoing"
      @click="emit('undo')"
    >
      撤销本次修复
    </el-button>
    <p v-else class="dfd-done__undone">本次修复已撤销</p>
  </div>
</template>

<script setup lang="ts">
import type { DanglingRefReattachResult } from "@/api/reconciliation";

/** 回补成功态（#2866）：显式给出 log_id，并把撤销做成唯一写动作。 */
defineProps<{
  result: DanglingRefReattachResult;
  undone: boolean;
  undoing: boolean;
}>();
const emit = defineEmits<{ undo: [] }>();
</script>

<style scoped>
.dfd-done p {
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.dfd-done__title {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-success-ink);
}

.dfd-done__undone {
  font-weight: 600;
  color: var(--color-info-ink);
}
</style>
