<script setup lang="ts">
/* eslint-disable vue/no-mutating-props -- 状态注入模式：data 为 composable 实例
   prop，currentPage 经 computed get/set 桥接（v-model:current-page） */
import { computed } from "vue";
import type { useWatchlistData } from "@/composables/useWatchlistData";

/**
 * 自选表格底栏（#980 P0-b 拆分自 index.vue，零行为变更）：
 * 左侧总数 + 右侧「每页条数（#1335 纯本地记忆）+ 翻页」。
 * 合规文案不放在本行（用户反馈放表格里很怪异），由页面底部 LayFooter 承担。
 */
const props = defineProps<{
  data: ReturnType<typeof useWatchlistData>;
}>();

// 状态注入模式：currentPage 为 composable 内部 ref，v-model 经 computed 桥接
const currentPage = computed({
  get: () => props.data.currentPage.value,
  set: (value: number) => {
    props.data.currentPage.value = value;
  }
});
</script>

<template>
  <!-- 表格底栏：左侧总数 + 右侧翻页，与表格之间用细分割线分区
       （design.md「卡片内分割线使用 --border-subtle 降低视觉权重」） -->
  <div class="table-footer">
    <span class="table-footer__total">共 {{ data.totalItems.value }} 条</span>
    <div class="table-footer__right">
      <!-- 每页条数选择（#1335）：纯本地记忆（localforage），不落数据库 -->
      <div class="page-size-select">
        <span class="page-size-select__label">每页</span>
        <el-select
          :model-value="data.pageSize.value"
          size="small"
          class="page-size-select__control"
          @change="data.setPageSize"
        >
          <el-option
            v-for="opt in data.pageSizeOptions"
            :key="opt"
            :label="opt"
            :value="opt"
          />
        </el-select>
      </div>
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="data.pageSize.value"
        :total="data.totalItems.value"
        layout="prev, pager, next"
        small
        background
        @current-change="() => data.fetchData(false)"
      />
    </div>
  </div>
</template>

<style scoped>
/* 表格底栏：2026-09-06 呼吸感回调。
   曾收紧到 padding-top 8 / margin-top 4 为表格让出首屏高度，结果「共 N 条」与
   翻页码紧贴分割线，底栏不像独立信息带而像表格长出的一条边。
   回到 padding-top 12（--space-3）/ margin-top 8（--space-2）：分割线上方留白
   足够，底栏与表格成为两个可分辨的区域。 */
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-3);
  margin-top: var(--space-2);
  border-top: 1px solid var(--border-light);
}

/* 底栏右侧：每页条数选择 + 翻页 成组右对齐 */
.table-footer__right {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}

/* 每页条数选择器（#1335）：与翻页器同高对齐，标签用次级/三级文字色 */
.page-size-select {
  display: flex;
  gap: 6px;
  align-items: center;
}

.page-size-select__label {
  font-size: 13px;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.page-size-select__control {
  width: 88px;
}

.table-footer__total {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}
</style>
