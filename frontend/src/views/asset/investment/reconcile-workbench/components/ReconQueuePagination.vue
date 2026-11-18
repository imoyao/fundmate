<template>
  <!--
    待办队列分页（owner 第二轮：「几百个待办全放一页，处理完还要往回滚」）。
    范式沿用同目录 DomainBDiscTable.vue 的客户端分页：small + background +
    total/prev/pager/next/sizes。筛选项变化时由 useReconQueue 把页码归 1。
  -->
  <el-pagination
    v-if="total > pageSize"
    class="recon-pagination"
    :current-page="page"
    :page-size="pageSize"
    :total="total"
    :page-sizes="[10, 20, 50]"
    layout="total, prev, pager, next, sizes"
    small
    background
    @current-change="onPage"
    @size-change="onSize"
  />
</template>

<script setup lang="ts">
defineOptions({ name: "ReconQueuePagination" });

defineProps<{
  page: number;
  pageSize: number;
  total: number;
}>();

const emit = defineEmits<{
  "update:page": [value: number];
  "update:pageSize": [value: number];
  changed: [];
}>();

function onPage(value: number): void {
  emit("update:page", value);
  emit("changed");
}

function onSize(value: number): void {
  emit("update:pageSize", value);
  emit("update:page", 1);
  emit("changed");
}
</script>

<style scoped>
.recon-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-standard);
}
</style>
