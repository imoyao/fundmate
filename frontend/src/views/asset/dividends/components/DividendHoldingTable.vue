<!--
  DividendHoldingTable · 逐持仓股息率（#872）

  数据由后端按「净分红降序」排好（每只在管持仓一行，含未分红的）——
  本组件不排序、不计算，只做单位换算与展示。
-->
<template>
  <CardBlock>
    <SectionHeader
      title="逐持仓股息率"
      :info="`股息率 = 近 ${months} 个月分红 / 当前持仓成本；分红包含现金分红与红利再投资，并扣除红利税`"
    >
      <template #action>
        <span class="holding-table__summary">
          {{ summaryText }}
        </span>
      </template>
    </SectionHeader>

    <el-table
      :data="holdings"
      size="small"
      empty-text="暂无在管持仓"
      class="holding-table"
    >
      <el-table-column label="产品" min-width="160">
        <template #default="{ row }">
          <ProductDisplay
            :name="row.name || row.symbol || '--'"
            :symbol="row.symbol || ''"
            :type-label="getTypeLabel(row.asset_type || '')"
            :show-code="!isCompositeAssetType(row.asset_type)"
          />
        </template>
      </el-table-column>

      <el-table-column label="持仓成本" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="centsToYuan(row.cost_cents)"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </template>
      </el-table-column>

      <el-table-column label="当前市值" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="centsToYuan(row.market_value_cents)"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </template>
      </el-table-column>

      <el-table-column :label="`近 ${months} 月分红`" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="centsToYuan(row.net_cents)"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </template>
      </el-table-column>

      <el-table-column label="股息率" width="100" align="right">
        <template #default="{ row }">
          <span class="holding-table__pct">
            {{ fmtPct(row.yield_on_cost_pct) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="累计现金分红" width="140" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="centsToYuan(row.all_time_cash_cents)"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </template>
      </el-table-column>

      <el-table-column label="再投浮盈" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="
              row.reinvest_gain_cents === null
                ? null
                : centsToYuan(row.reinvest_gain_cents)
            "
            size="sm"
          />
        </template>
      </el-table-column>

      <el-table-column label="最近分红" width="110" align="right">
        <template #default="{ row }">
          <span class="holding-table__date">
            {{ row.last_dividend_date || "--" }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import { getTypeLabel } from "@/constants/assetType";
import { isCompositeAssetType } from "@/constants/advisorPlatform";
import { centsToYuan } from "@/utils/currency";
import type { DividendHolding, DividendPortfolio } from "@/api/dividends";

const props = defineProps<{
  holdings: DividendHolding[];
  portfolio: DividendPortfolio;
  months: number;
}>();

/** 比率：后端 `null` = 分母非正（无成本），显示占位而不显示 0 */
function fmtPct(value: number | null): string {
  return value === null ? "--" : `${value.toFixed(2)}%`;
}

const summaryText = computed(
  () =>
    `${props.portfolio.paying_count} / ${props.portfolio.holding_count} 只在分红`
);
</script>

<style lang="scss" scoped>
.holding-table {
  width: 100%;
}

.holding-table__summary {
  font-size: 12px;
  color: var(--text-tertiary);
}

.holding-table__pct,
.holding-table__date {
  font-family: var(--font-mono);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.holding-table__date {
  color: var(--text-secondary);
}
</style>
