<template>
  <div
    class="rounded-xl p-6 sm:p-8 flex flex-col mt-4"
    :style="{
      backgroundColor: 'var(--bg-card)',
      border: '1px solid var(--border-default)',
      boxShadow: 'var(--shadow-raised)'
    }"
  >
    <el-table
      v-loading="loading"
      height="400"
      :data="positions"
      style="width: 100%"
      :header-cell-style="INVENTORY_TABLE_HEADER_STYLE"
      :cell-style="INVENTORY_TABLE_CELL_STYLE"
    >
      <el-table-column label="产品信息" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <ProductDisplay
            :name="row.name"
            :symbol="row.symbol"
            :type-label="row.type_label"
          />
        </template>
      </el-table-column>
      <el-table-column prop="account_name" label="归属账户" width="120" />
      <el-table-column label="市值" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.market_value"
            :show-sign="false"
            size="sm"
          />
        </template>
      </el-table-column>
      <el-table-column label="盈亏" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay :value="row.pnl" :show-sign="true" size="sm" />
        </template>
      </el-table-column>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination
        :current-page="page"
        :page-size="INVESTMENT_PAGE_SIZE"
        :total="total"
        layout="prev, pager, next"
        small
        @current-change="emit('update:page', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 投资理财 · 持仓明细表（后端分页）。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。纯展示 + 翻页事件，
 * 数据由页面数据层提供（`useInventoryData`），本组件不发请求。
 */
import type { Position } from "@/api/types";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import {
  INVESTMENT_PAGE_SIZE,
  INVENTORY_TABLE_CELL_STYLE,
  INVENTORY_TABLE_HEADER_STYLE
} from "../constants";

defineProps<{
  /** 当前页持仓明细 */
  positions: Position[];
  /** 总条数（分页器用） */
  total: number;
  /** 表格 loading */
  loading: boolean;
  /** 当前页码 */
  page: number;
}>();

const emit = defineEmits<{
  "update:page": [page: number];
}>();
</script>

<style scoped>
/* 表格行高增加，提升呼吸感 */
:deep(.el-table__body td) {
  padding-top: 14px;
  padding-bottom: 14px;
}

:deep(.el-table__header th) {
  padding-top: 12px;
  padding-bottom: 12px;
}

:deep(.el-table td) {
  border-bottom-color: var(--border-light);
}

:deep(.el-table__body tr:hover > td) {
  background-color: var(--bg-hover) !important;
}
</style>
