<!--
  LeaveGuardDialog · 离开导入页三选确认（#1789）

  不用 ElMessageBox 的原因（沿 #1830 结论）：需要「保存后离开 / 丢弃 / 取消」三个动作位，
  ElMessageBox 只有确认/取消两个槽，装不下「两个分支 + 中止」——把中止位借给某个分支
  正是 #1830 事故的成因。范式与 DeletePositionDialog（删除持仓）一致。
-->
<template>
  <el-dialog
    :model-value="visible"
    title="离开导入页面？"
    width="440px"
    destroy-on-close
    :close-on-click-modal="false"
    @update:model-value="emit('update:visible', $event)"
  >
    <p class="leave-guard-body">
      当前有未保存的导入修改（草稿每 30 秒自动保存一次），请选择离开方式。
    </p>

    <template #footer>
      <div class="leave-guard-actions">
        <el-button @click="emit('cancel')">取消</el-button>
        <el-button type="danger" @click="emit('discard')">丢弃</el-button>
        <el-button type="primary" @click="emit('save')">保存后离开</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
defineProps<{ visible: boolean }>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
  /** 保存当前修改后离开 */
  save: [];
  /** 丢弃整份草稿（含已保存的）后离开 */
  discard: [];
  /** 取消离开，留在本页 */
  cancel: [];
}>();
</script>

<style scoped>
.leave-guard-body {
  margin: 0 0 4px;
  font-size: var(--text-small);
  color: var(--text-secondary);
}

.leave-guard-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
