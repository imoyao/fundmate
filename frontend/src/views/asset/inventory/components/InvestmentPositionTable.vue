<template>
  <CardBlock class="flex flex-col">
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
            :value="marketValue(row as Position)"
            :show-sign="false"
            size="sm"
          />
        </template>
      </el-table-column>
      <!-- 盈亏双线（#1104）：主行＝已确认（T-1 净值 / 收盘价口径，后端权威值），
           副行＝当日预估（前端实时链路，带「估」标记）。两行同显见 PnlDualLine 头注释。 -->
      <el-table-column label="盈亏" width="170" align="right">
        <template #default="{ row }">
          <PnlDualLine
            :confirmed="confirmedPnl(row as Position)"
            :estimated="valuation.estimatedPnl(row as Position)"
            :hint="valuation.estimateHint(row as Position)"
          />
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
  </CardBlock>
</template>

<script setup lang="ts">
/**
 * 投资理财 · 持仓明细表（后端分页）。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。纯展示 + 翻页事件，
 * 数据由页面数据层提供（`useInventoryData`），本组件不发请求。
 *
 * #1501：外层卡片容器收敛为 `CardBlock`，表格视觉基线（边框 / hover / 行高）
 * 一律走 `src/style/el-table.css`，本组件不再写 `:deep(.el-table ...)`。
 *
 * #1104：盈亏列改为「已确认 / 预估」双线（`PnlDualLine`）。估值实例由页面注入
 * （`valuation` prop，与自选页注入 `realtime` 同模式），本组件仍不持业务状态。
 */
import type { Position } from "@/api/types";
import CardBlock from "@/components/CardBlock/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import PnlDualLine from "@/components/PnlDualLine/index.vue";
import {
  confirmedPnl,
  type PositionValuation
} from "@/composables/usePositionValuation";
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
  /** 盈亏双线的估值接线（页面注入；组件不取数） */
  valuation: PositionValuation;
}>();

const emit = defineEmits<{
  "update:page": [page: number];
}>();

/**
 * 市值：优先后端 `market_value`，缺失时用「数量 × 现价」回退。
 *
 * 后端分页路径（`GET /api/positions/`）实测不产出 `market_value`（见 `api/types.d.ts`
 * 的 Position 注释），缺回退会让整列恒显示 `--`；而该列口径与盈亏主行同源
 * （都用 `current_price`），回退值与右列的已确认盈亏自洽，不会出现「市值有值、盈亏为 0」
 * 自相矛盾的行。
 */
function marketValue(row: Position): number | null {
  if (row.market_value != null) return row.market_value;
  const quantity = Number(row.quantity ?? 0);
  const current = Number(row.current_price ?? 0);
  if (!(quantity > 0) || !(current > 0)) return null;
  return quantity * current;
}
</script>
