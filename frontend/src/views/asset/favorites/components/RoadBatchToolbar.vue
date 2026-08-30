<!--
  RoadBatchToolbar · 管理态工具栏

  进入管理模式后吸顶在瀑布流上方：已选 N 项 + 批量置顶 / 批量移出 / 全选 / 取消。
  批量操作只针对有真实自选记录（id 非空）的卡片，示例卡不计入。
-->
<template>
  <div class="road-batch">
    <span class="road-batch__count">
      已选 <strong>{{ selectedCount }}</strong> 项
    </span>
    <div class="road-batch__ops">
      <el-button size="small" text @click="$emit('select-all')"
        >全选本页</el-button
      >
      <el-button size="small" text @click="$emit('clear')">取消选择</el-button>
      <el-button
        size="small"
        type="primary"
        plain
        :disabled="!selectedCount"
        @click="$emit('batch-pin')"
        >批量置顶</el-button
      >
      <el-button
        size="small"
        type="danger"
        plain
        :disabled="!selectedCount"
        @click="$emit('batch-remove')"
        >批量移出</el-button
      >
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ selectedCount: number }>();

defineEmits<{
  (e: "select-all"): void;
  (e: "clear"): void;
  (e: "batch-pin"): void;
  (e: "batch-remove"): void;
}>();
</script>

<style scoped>
.road-batch {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: var(--brand-100);
  border: 1px solid var(--brand-400);
  border-radius: var(--radius-md);
}

.road-batch__count {
  font-size: 13px;
  color: var(--text-secondary);
}

.road-batch__count strong {
  font-family: var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
  color: var(--brand-700);
}

.road-batch__ops {
  display: flex;
  gap: 6px;
  align-items: center;
}
</style>
