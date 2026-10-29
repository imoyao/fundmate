<!--
  ClearedCyclesSection · 清仓周期复盘（#2131 · 账本对齐 A'）

  挂在「复盘」页（route /analysis）：该页定位是「时间维度上的表现：净值怎么走、
  收益从哪来」，而清仓周期回答的正是「已落袋的那部分表现从哪来」——同页不另开路由。

  数据：GET /api/summary/cleared-cycles/（只读现算）。本组件不排序、不计算，
  只做单位与占位展示；null 一律 "--"（部分配对周期不可算，不是 0）。

  与产品详情页 Pro 卡（ProductProPerformance · analytics/behavior.py）的分工：
  那边观察单位是 FIFO 卖出笔（单标的），这边是清仓周期（全账户列表+汇总），
  同一套后端 FIFO 口径，勿在本组件再造第二套。
-->
<template>
  <section>
    <SectionHeader title="清仓周期复盘" :info="sectionInfo">
      <template #action>
        <span class="cleared-cycles__count">
          {{ summary.cycle_count }} 个周期
        </span>
      </template>
    </SectionHeader>

    <MetricGrid>
      <!-- 主数字统一 --brand-ink（WCAG AA：白底 5.86:1）；不用 --brand-700（3.73:1 不达标） -->
      <MetricCard
        title="累计已实现盈亏"
        :value="pnlTotalLabel"
        featured
        value-color="var(--brand-ink)"
        :caption="pnlTotalCaption(summary)"
      />
      <MetricCard
        title="胜率"
        :value="winRateLabel"
        unit="%"
        value-color="var(--brand-ink)"
        :caption="winRateCaption"
      />
      <MetricCard
        title="盈亏比"
        :value="ratioLabel"
        value-color="var(--brand-ink)"
        caption="平均盈利 / 平均亏损"
      />
      <MetricCard
        title="平均持有天数"
        :value="avgHoldingLabel"
        unit="天"
        value-color="var(--brand-ink)"
        caption="按周期简单平均"
      />
    </MetricGrid>

    <CardBlock>
      <el-table
        :data="cycles"
        size="small"
        empty-text="暂无已清仓周期（标的卖出且份额归零后自动归档）"
      >
        <el-table-column label="产品" min-width="160">
          <template #default="{ row }">
            <ProductDisplay
              compact
              :name="row.name || row.symbol || '--'"
              :symbol="row.symbol || ''"
            />
          </template>
        </el-table-column>

        <el-table-column label="首买日" width="120">
          <template #default="{ row }">
            {{ row.first_buy_date || "--" }}
          </template>
        </el-table-column>

        <el-table-column label="末卖日" width="120">
          <template #default="{ row }">
            {{ row.last_sell_date || "--" }}
          </template>
        </el-table-column>

        <el-table-column label="持有天数" width="100" align="right">
          <template #default="{ row }">
            {{ fmtHoldingDays(row.avg_holding_days) }}
          </template>
        </el-table-column>

        <el-table-column label="交易次数" width="90" align="right">
          <template #default="{ row }">
            {{ row.trade_count }}
          </template>
        </el-table-column>

        <el-table-column label="已实现盈亏" width="130" align="right">
          <template #default="{ row }">
            <MoneyDisplay
              :value="row.realized_pnl"
              show-sign
              auto-color
              size="sm"
            />
          </template>
        </el-table-column>

        <el-table-column label="盈亏率" width="100" align="right">
          <template #default="{ row }">
            <RiseFallText
              v-if="row.pnl_pct !== null"
              :value="row.pnl_pct"
              size="sm"
            />
            <span v-else class="cleared-cycles__na">--</span>
          </template>
        </el-table-column>
      </el-table>
    </CardBlock>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import { formatAmount } from "@/utils/currency";
import {
  getClearedCycles,
  type ClearedCycle,
  type ClearedCyclesSummary
} from "@/api/summary";
import {
  fmtHoldingDays,
  fmtHoldingDaysValue,
  fmtRatio,
  pnlTotalCaption
} from "./helpers";

defineOptions({ name: "ClearedCyclesSection" });

const cycles = ref<ClearedCycle[]>([]);
const summary = ref<ClearedCyclesSummary>({
  cycle_count: 0,
  sample_count: 0,
  win_count: 0,
  loss_count: 0,
  win_rate: null,
  profit_loss_ratio: null,
  avg_holding_days: null,
  realized_pnl_total: null,
  total_trade_count: 0,
  caveats: []
});

/** 接口失败：区块照常渲染空态（各区块独立降级，不阻塞复盘页其余内容） */
const load = async () => {
  try {
    const res = await getClearedCycles();
    const data = res?.data;
    cycles.value = data?.cycles ?? [];
    if (data?.summary) summary.value = data.summary;
  } catch {
    cycles.value = [];
  }
};

onMounted(load);

const formatYuan = (n: number) => `¥${formatAmount(n || 0)}`;
const formatSignedYuan = (n: number) =>
  `${n >= 0 ? "+" : "-"}${formatYuan(Math.abs(n || 0))}`;

const pnlTotalLabel = computed(() =>
  summary.value.realized_pnl_total === null
    ? null
    : formatSignedYuan(summary.value.realized_pnl_total)
);
const winRateLabel = computed(() => fmtRatio(summary.value.win_rate));
const ratioLabel = computed(() => fmtRatio(summary.value.profit_loss_ratio));
const avgHoldingLabel = computed(() => {
  const days = fmtHoldingDaysValue(summary.value.avg_holding_days);
  return days === null ? null : String(days);
});
const winRateCaption = computed(() => {
  const s = summary.value;
  if (s.sample_count === 0) return "暂无已完结周期";
  return `胜 ${s.win_count} / 负 ${s.loss_count}（样本 ${s.sample_count}）`;
});

const sectionInfo = computed(() => {
  const s = summary.value;
  const base =
    "按「首买→末卖」周期统计已落袋表现：盈亏由 FIFO 配对自算（不读流水 realized_pnl 列，存量库该列全 0）；默认剔除货币基金/逆回购/现金";
  if (s.cycle_count > s.sample_count) {
    return `${base}；${s.cycle_count - s.sample_count} 个周期因部分配对（先卖后买/无买入流水）不可算，未计入汇总`;
  }
  return base;
});
</script>

<style scoped>
.cleared-cycles__count {
  font-size: var(--el-font-size-small);
  color: var(--text-tertiary-ink);
}

.cleared-cycles__na {
  color: var(--text-tertiary-ink);
}
</style>
