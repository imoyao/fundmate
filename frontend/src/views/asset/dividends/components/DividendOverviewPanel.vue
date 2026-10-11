<!--
  DividendOverviewPanel · 分红总览（#872）

  只消费 `GET /api/dividends/summary/` 的返回，不自行做任何口径计算：
  金额一律整数分 → 经 `centsToYuan` 换算后交给 `MoneyDisplay`；
  比率（`*_pct`）后端已按「百分比数值」给出，`null` 表示分母非正（无成本），显示 `--`。
-->
<template>
  <div class="overview">
    <!-- 1. 本期分红金额 -->
    <CardBlock>
      <SectionHeader
        :title="`近 ${summary.period.months} 个月分红`"
        info="净分红 = 现金分红 + 红利再投资 − 红利税；红利再投资虽未落袋为现金，但份额已增加，同属分红权益"
      />

      <div class="overview__hero">
        <span class="overview__hero-label">净分红</span>
        <MoneyDisplay
          :value="centsToYuan(summary.totals.ttm.net_cents)"
          :show-sign="false"
          :auto-color="false"
          size="hero"
        />
        <span class="overview__hero-range">
          {{ summary.period.start }} ~ {{ summary.period.end }}
        </span>
      </div>

      <div class="overview__cols">
        <div class="overview__col">
          <span class="overview__col-label">现金分红</span>
          <MoneyDisplay
            :value="centsToYuan(summary.totals.ttm.cash_cents)"
            :show-sign="false"
            :auto-color="false"
            size="lg"
          />
        </div>
        <div class="overview__col">
          <span class="overview__col-label">红利再投资</span>
          <MoneyDisplay
            :value="centsToYuan(summary.totals.ttm.reinvest_cents)"
            :show-sign="false"
            :auto-color="false"
            size="lg"
          />
        </div>
        <div class="overview__col">
          <span class="overview__col-label">红利税</span>
          <MoneyDisplay
            :value="centsToYuan(summary.totals.ttm.tax_cents)"
            :show-sign="false"
            :auto-color="false"
            size="lg"
          />
        </div>
        <div class="overview__col">
          <span class="overview__col-label">再投浮盈</span>
          <MoneyDisplay
            :value="
              summary.portfolio.reinvest_gain_cents === null
                ? null
                : centsToYuan(summary.portfolio.reinvest_gain_cents)
            "
            size="lg"
          />
        </div>
      </div>
    </CardBlock>

    <!-- 2. 股息率指标 -->
    <MetricGrid>
      <MetricCard
        title="组合股息率"
        :value="fmtPct(summary.portfolio.yield_on_cost_pct)"
        unit="%"
        featured
        :caption="`净分红 / 持仓成本 · ${summary.portfolio.paying_count} / ${summary.portfolio.holding_count} 只在分红`"
      />
      <MetricCard
        title="现金股息率"
        :value="fmtPct(summary.portfolio.cash_yield_on_cost_pct)"
        unit="%"
        caption="仅现金分红 / 持仓成本"
      />
      <MetricCard
        title="市值口径股息率"
        :value="fmtPct(summary.portfolio.yield_on_value_pct)"
        unit="%"
        caption="净分红 / 当前持仓市值"
      />
      <MetricCard
        title="累计分红"
        :value="formatAmount(centsToYuan(summary.totals.all_time.net_cents))"
        unit="元"
        :caption="allTimeCaption"
      />
    </MetricGrid>

    <!-- 3. 股息目标 -->
    <DividendTargetCard
      :target="summary.target"
      :actual-pct="summary.portfolio.yield_on_cost_pct"
      :months="summary.period.months"
      @saved="emit('saved')"
    />

    <!-- 4. 逐年分红 -->
    <CardBlock>
      <SectionHeader
        title="逐年分红"
        info="全量流水口径：含已清仓持仓与未关联持仓的分红"
      />
      <el-table
        v-if="summary.by_year.length > 0"
        :data="summary.by_year"
        size="small"
        class="overview__table"
      >
        <el-table-column prop="year" label="年度" width="90" />
        <el-table-column label="现金分红" align="right">
          <template #default="{ row }">
            <MoneyDisplay
              :value="centsToYuan(row.cash_cents)"
              :show-sign="false"
              :auto-color="false"
              size="sm"
            />
          </template>
        </el-table-column>
        <el-table-column label="红利再投" align="right">
          <template #default="{ row }">
            <MoneyDisplay
              :value="centsToYuan(row.reinvest_cents)"
              :show-sign="false"
              :auto-color="false"
              size="sm"
            />
          </template>
        </el-table-column>
        <el-table-column label="红利税" align="right">
          <template #default="{ row }">
            <MoneyDisplay
              :value="centsToYuan(row.tax_cents)"
              :show-sign="false"
              :auto-color="false"
              size="sm"
            />
          </template>
        </el-table-column>
        <el-table-column label="净分红" align="right">
          <template #default="{ row }">
            <MoneyDisplay
              :value="centsToYuan(row.net_cents)"
              :show-sign="false"
              :auto-color="false"
              size="sm"
            />
          </template>
        </el-table-column>
        <el-table-column
          prop="event_count"
          label="笔数"
          width="80"
          align="right"
        />
      </el-table>
      <p v-else class="overview__empty">
        还没有分红记录。导入交易流水或由同步任务抓取分红后，这里会按年汇总。
      </p>
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { centsToYuan, formatAmount } from "@/utils/currency";
import type { DividendSummary } from "@/api/dividends";
import DividendTargetCard from "./DividendTargetCard.vue";

const props = defineProps<{ summary: DividendSummary }>();

const emit = defineEmits<{ saved: [] }>();

/** 比率展示：后端用 null 表示「分母非正、不可算」，此处保持占位语义而非显示 0 */
function fmtPct(value: number | null): string | null {
  return value === null ? null : value.toFixed(2);
}

const allTimeCaption = computed(() => {
  const { first_date: first, last_date: last } = props.summary.totals;
  if (!first || !last) return "历史累计（无记录）";
  return `历史累计 · ${first} 至 ${last}`;
});
</script>

<style lang="scss" scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: var(--space-section);
}

.overview__hero {
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
}

.overview__hero-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.overview__hero-range {
  font-size: 12px;
  color: var(--text-tertiary);
}

.overview__cols {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-5);
  margin-top: var(--space-3);
}

.overview__col {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 160px;
}

.overview__col-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.overview__table {
  width: 100%;
}

.overview__empty {
  font-size: 13px;
  color: var(--text-tertiary);
}
</style>
