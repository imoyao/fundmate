<!--
  DeletePositionDialog · 删除持仓确认（#1830）

  不用 ElMessageBox 的原因：旧实现把 cancelButtonText 写成「仅删除持仓」，把用户心智里的
  「中止位」变成一次真实删除。ElMessageBox 只有确认/取消两个槽，装不下「两个删除分支 + 中止」。
  范式与同目录 DeleteLedgerDialog（删除账户）一致。
-->
<template>
  <el-dialog
    :model-value="visible"
    title="删除持仓"
    width="420px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <p class="mb-2" :style="{ color: 'var(--text-primary)' }">
      确定删除持仓「<strong>{{ positionName }}</strong
      >」吗？
    </p>
    <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
      <strong>仅删除持仓</strong>：保留该持仓的交易记录，之后仍可在流水里看到。
      <br />
      <strong>删除持仓及交易</strong>：一并删除关联交易，不可恢复。
    </p>

    <template #footer>
      <div class="flex items-center justify-end gap-2">
        <el-button @click="emit('update:visible', false)">取消</el-button>
        <el-button
          :loading="loading"
          :disabled="loading"
          @click="emit('confirm', { keepTransactions: true })"
        >
          仅删除持仓
        </el-button>
        <el-button
          type="danger"
          :loading="loading"
          :disabled="loading"
          @click="emit('confirm', { keepTransactions: false })"
        >
          删除持仓及交易
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean;
  positionName: string;
  loading?: boolean;
}>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
  /** keepTransactions=true → 仅删持仓保留交易；false → 连交易一起删 */
  confirm: [payload: { keepTransactions: boolean }];
}>();
</script>
