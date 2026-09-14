<template>
  <CardBlock>
    <el-table
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
            :type-label="getMinorAssetLabel(row as AssetRecord)"
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
      <el-table-column label="金额" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.signed_amount"
            :show-sign="false"
            size="sm"
          />
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
  </CardBlock>
</template>

<script setup lang="ts">
/**
 * 投资理财 · 「其他投资」资产明细表。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。承载非交易类投资理财资产
 * （#1354：银行理财 / 投顾 / 信托 / 私募 / 理财型保险等存量大类），
 * 细分标签优先取 `minor_category`，存量数据回退历史大类标签。
 *
 * #1501：外层卡片容器收敛为 `CardBlock`，表格视觉基线（边框 / hover / 行高）
 * 一律走 `src/style/el-table.css`，本组件不再写 `:deep(.el-table ...)`。
 */
import type { AssetRecord } from "@/api/assets";
import CardBlock from "@/components/CardBlock/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import {
  INVENTORY_TABLE_CELL_STYLE,
  INVENTORY_TABLE_HEADER_STYLE
} from "../constants";
import { getMinorAssetLabel } from "../helpers";

defineProps<{
  /** 当前大类下的资产明细（调用方保证非空才渲染本组件） */
  assets: AssetRecord[];
}>();

const emit = defineEmits<{
  /** 点击行内「编辑」 */
  edit: [row: AssetRecord];
  /** 点击行内「删除」（二次确认由页面负责） */
  remove: [row: AssetRecord];
}>();
</script>
