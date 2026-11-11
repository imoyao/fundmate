<template>
  <CardBlock v-if="assets.length > 0">
    <el-table
      :height="assets.length >= 5 ? 400 : null"
      :data="assets"
      style="width: 100%"
      :header-cell-style="INVENTORY_TABLE_HEADER_STYLE"
      :cell-style="INVENTORY_TABLE_CELL_STYLE"
    >
      <el-table-column label="资产名称" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <!-- 资产没有「代码」这一说：`AssetRecord` / 后端 `AssetOut` 都不含 `symbol`，
               而 ProductDisplay 在代码为空时会渲染 `# --` 占位——在「资产名称」下是纯
               噪音（盘点页固定资产行实测），故显式关闭代码段，只留名称 + 大类标签。 -->
          <ProductDisplay
            :name="row.name"
            :show-code="false"
            :type-label="row.type_label"
          />
        </template>
      </el-table-column>
      <el-table-column
        prop="account_name"
        label="归属账户"
        min-width="140"
        show-overflow-tooltip
      >
        <template #default="{ row }">{{
          row.account_name || "未指定"
        }}</template>
      </el-table-column>
      <el-table-column label="大类" min-width="110">
        <template #default="{ row }">
          {{ getCategoryLabel(row.major_category) }}
        </template>
      </el-table-column>
      <el-table-column label="金额" min-width="150" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.signed_amount"
            :show-sign="true"
            size="sm"
          />
        </template>
      </el-table-column>
      <el-table-column label="配置目标" min-width="120" align="center">
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
      <!-- 操作列：三个动作都是「对这条资产做点什么」，用文字更直接（`明细` 没有无歧义
           图标，换图标必须配 tooltip，反而多一次悬停）。单行不换行由共享样式类
           `table-row-actions` 承担（`src/style/el-table.css`），与持仓明细表同一范式。
           宽度 180 = 三个 12px 两字按钮（各 46）+ 两个 4px 间距（8）≈ 146，
           加左右单元格内边距 24 后仍有余量。 -->
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <div class="table-row-actions">
            <el-button
              text
              size="small"
              @click="emit('edit', row as AssetRecord)"
              >编辑</el-button
            >
            <el-button
              text
              size="small"
              @click="emit('detail', row as AssetRecord)"
              >明细</el-button
            >
            <el-button
              text
              size="small"
              type="danger"
              @click="emit('remove', row as AssetRecord)"
              >删除</el-button
            >
          </div>
        </template>
      </el-table-column>
    </el-table>
  </CardBlock>

  <!-- 空状态是虚线占位框，不是「区块卡」，故不走 CardBlock（CardBlock 为实线边框） -->
  <div
    v-else
    class="rounded-xl py-6 sm:py-8 px-10 text-center border border-dashed"
    :style="{
      borderColor: 'var(--border-default)',
      backgroundColor: 'var(--bg-card)'
    }"
  >
    <p :style="{ color: 'var(--text-tertiary-ink)' }">暂无此分类下的资产记录</p>
  </div>
</template>

<script setup lang="ts">
/**
 * 非投资理财大类的资产明细表（含空状态）。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。比「其他投资」表多出
 * 「大类」与「配置目标」两列，故与 `OtherInvestmentTable` 分列而非用 props 分支揉成一个。
 * 空状态（无记录）由本组件内聚，避免调用方重复写「有数据才渲染」的判断。
 *
 * #1501：表格卡片容器收敛为 `CardBlock`，表格视觉基线（边框 / hover / 行高）
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
  /** 点击行内「明细」：打开单资产值变动时间线抽屉 */
  detail: [row: AssetRecord];
  /** 点击行内「删除」（二次确认由页面负责） */
  remove: [row: AssetRecord];
}>();
</script>
