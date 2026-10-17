<template>
  <CardBlock>
    <el-table
      v-loading="loading"
      :data="items"
      style="width: 100%"
      :header-cell-style="INVENTORY_TABLE_HEADER_STYLE"
      :cell-style="INVENTORY_TABLE_CELL_STYLE"
    >
      <el-table-column label="产品信息" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <ProductDisplay
            :name="row.name"
            :symbol="row.symbol || ''"
            :type-label="row.asset_type_label"
          />
        </template>
      </el-table-column>
      <el-table-column
        prop="ledger_name"
        label="归属账户"
        width="130"
        show-overflow-tooltip
      />
      <el-table-column label="本金" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay :value="row.net_amount" :show-sign="false" size="sm" />
        </template>
      </el-table-column>
      <el-table-column label="累计收益" width="120" align="right">
        <template #default="{ row }">
          <MoneyDisplay :value="row.income_amount" size="sm" />
        </template>
      </el-table-column>
      <el-table-column label="合计" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.total_amount"
            :show-sign="false"
            size="sm"
          />
        </template>
      </el-table-column>

      <template #append>
        <div class="cash-like-footer">
          <span class="cash-like-footer__label">类现金合计</span>
          <span class="cash-like-footer__value">
            <MoneyDisplay :value="total" :show-sign="false" />
          </span>
          <span class="cash-like-footer__hint">
            按流水净额记账（不折算份额），金额已计入总资产，此处不重复加总
          </span>
        </div>
      </template>
    </el-table>
  </CardBlock>
</template>

<script setup lang="ts">
/**
 * 投资理财 · 「类现金」分组（2026-10-17）。
 *
 * 货基 / 逆回购在本仓**不建持仓行**（`position_id IS NULL` 的孤儿流水，
 * 口径见 `summary_service.orphan_money_fund_totals_by_ledger`），因此不会出现在
 * 上面的持仓明细表里，但它们是真实资产、已计入总资产。
 *
 * 这张表只回答「这些钱分别躺在哪个账户的哪个产品上」：
 * ① 只展示、不参与持仓盈亏与占比；② 金额不得再加进页面任何合计（双计）。
 *
 * 数据源 `GET /api/summary/cash-like/`（家庭级，按「账户 + 产品」归组）。
 */
import CardBlock from "@/components/CardBlock/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import type { CashLikeItem } from "@/api/summary";
import {
  INVENTORY_TABLE_CELL_STYLE,
  INVENTORY_TABLE_HEADER_STYLE
} from "../constants";

defineProps<{
  /** 类现金明细（调用方保证非空才渲染本组件） */
  items: CashLikeItem[];
  /** 合计（本金 + 收益，元） */
  total: number;
  loading?: boolean;
}>();
</script>

<style scoped lang="scss">
.cash-like-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
  padding: 10px 12px;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.cash-like-footer__label {
  font-weight: 600;
  color: var(--text-primary);
}

.cash-like-footer__value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.cash-like-footer__hint {
  color: var(--text-tertiary-ink);
}
</style>
