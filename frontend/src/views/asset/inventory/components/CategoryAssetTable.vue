<template>
  <div
    v-if="assets.length > 0"
    class="rounded-xl p-6 sm:p-8"
    :style="{
      backgroundColor: 'var(--bg-card)',
      border: '1px solid var(--border-default)',
      boxShadow: 'var(--shadow-raised)'
    }"
  >
    <el-table
      :height="assets.length >= 5 ? 400 : null"
      :data="assets"
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
      <el-table-column
        prop="account_name"
        label="归属账户"
        width="120"
        show-overflow-tooltip
      >
        <template #default="{ row }">{{
          row.account_name || "未指定"
        }}</template>
      </el-table-column>
      <el-table-column label="大类" width="100">
        <template #default="{ row }">
          {{ getCategoryLabel(row.major_category) }}
        </template>
      </el-table-column>
      <el-table-column label="金额" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.signed_amount"
            :show-sign="true"
            size="sm"
          />
        </template>
      </el-table-column>
      <el-table-column label="配置目标" width="100" align="center">
        <template #default="{ row }">
          <span
            class="px-2 py-0.5 rounded-full text-xs"
            :style="{
              backgroundColor: getAllocationBgColor(row.allocation),
              color: getAllocationColor(row.allocation)
            }"
          >
            {{ getAllocationLabel(row.allocation) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button text size="small" @click="emit('edit', row as AssetRecord)"
            >编辑</el-button
          >
          <el-button
            text
            size="small"
            type="danger"
            @click="emit('remove', row as AssetRecord)"
            >删除</el-button
          >
        </template>
      </el-table-column>
    </el-table>
  </div>

  <div
    v-else
    class="rounded-xl py-6 sm:py-8 px-10 text-center border border-dashed mt-4"
    :style="{
      borderColor: 'var(--border-default)',
      backgroundColor: 'var(--bg-card)'
    }"
  >
    <p :style="{ color: 'var(--text-tertiary)' }">暂无此分类下的资产记录</p>
  </div>
</template>

<script setup lang="ts">
/**
 * 非投资理财大类的资产明细表（含空状态）。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。比「其他投资」表多出
 * 「大类」与「配置目标」两列，故与 `OtherInvestmentTable` 分列而非用 props 分支揉成一个。
 * 空状态（无记录）由本组件内聚，避免调用方重复写「有数据才渲染」的判断。
 */
import type { AssetRecord } from "@/api/assets";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import {
  INVENTORY_TABLE_CELL_STYLE,
  INVENTORY_TABLE_HEADER_STYLE
} from "../constants";
import {
  getCategoryLabel,
  getAllocationBgColor,
  getAllocationColor,
  getAllocationLabel
} from "../helpers";

defineProps<{
  /** 当前大类下的资产明细（空数组时渲染空状态） */
  assets: AssetRecord[];
}>();

const emit = defineEmits<{
  /** 点击行内「编辑」 */
  edit: [row: AssetRecord];
  /** 点击行内「删除」（二次确认由页面负责） */
  remove: [row: AssetRecord];
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
