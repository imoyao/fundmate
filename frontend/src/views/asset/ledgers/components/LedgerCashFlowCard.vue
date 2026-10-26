<!--
  账户详情页「资金流动」区块（#2616，后端 GET /api/summary/cash-flow/）。

  回答的是收益率回答不了的那个问题：「这个账户我一共投进去多少、取出来多少、
  现在值多少、到底赚了多少」。收益率高不代表投入规模合适，只有资金流动能回答。

  口径纪律（docs/spec/cashflow-layers.md，禁止在本组件里改口径）：
  - 入金/出金（L1）才是资金进出；买入/卖出是账户内换形态（L2），不计入这两个数；
  - 净投入 = 入金 − 出金，恒为「自开户以来」，**切区间不会变小**；
  - 净值线是持仓市值口径，现金残差是**推导值**，单独展示、不进曲线；
  - 缺价日 `net_worth = null` 保持断线，**绝不补 0**（补 0 等于把「没数据」画成「持平」）。
-->
<template>
  <CardBlock class="cash-flow">
    <SectionHeader title="资金流动">
      <template #info>
        <p>
          入金 /
          出金只统计**跨出本账户**的钱；买入、卖出是账户内部换形态，不算。
        </p>
        <p>净投入 = 累计入金 − 累计出金，自开户以来统计，不随时间区间变化。</p>
        <p>
          净值线为**持仓市值**；现金残差
          <strong>{{ money(totals?.cash_residual) }}</strong>
          由流水推导（缺流水会偏），未计入曲线。
        </p>
      </template>
      <template #action>
        <SegmentedControl
          v-model="rangeDays"
          :options="RANGE_OPTIONS"
          size="small"
          aria-label="资金流动区间"
        />
      </template>
    </SectionHeader>

    <p v-if="loadError" class="cash-flow__error">{{ loadError }}</p>

    <template v-else>
      <div class="cash-flow__metrics">
        <div class="metric">
          <span class="metric__label">累计入金</span>
          <span class="metric__value">{{ money(totals?.deposit) }}</span>
        </div>
        <div class="metric">
          <span class="metric__label">累计出金</span>
          <span class="metric__value">{{ money(totals?.withdraw) }}</span>
        </div>
        <div class="metric metric--key">
          <span class="metric__label">净投入</span>
          <span class="metric__value">{{ money(totals?.net_invested) }}</span>
        </div>
        <div class="metric metric--key">
          <span class="metric__label">期末资产</span>
          <span class="metric__value">{{ money(totals?.end_asset) }}</span>
        </div>
      </div>

      <!-- 缺入金记录：净投入恒 0，必须说清是「没录」而不是「没赚钱」 -->
      <p
        v-if="data && totals && !totals.has_deposit_record"
        class="cash-flow__hint"
      >
        该账户还没有入金记录，净投入按 0 展示——补录入金后，这里的收益才有意义。
      </p>

      <div class="cash-flow__chart">
        <v-chart
          :option="lineOption"
          :autoresize="true"
          class="chart chart--line"
        />
      </div>

      <div class="cash-flow__legend">
        <span class="legend legend--worth">持仓市值</span>
        <span class="legend legend--invested">累计净投入</span>
        <span v-if="missingDays > 0" class="legend legend--missing">
          {{ missingDays }} 天无价格（断线，不补 0）
        </span>
      </div>

      <div class="cash-flow__chart">
        <v-chart
          :option="barOption"
          :autoresize="true"
          class="chart chart--bar"
        />
      </div>

      <p class="cash-flow__caliber">
        期末资产 = 持仓市值 + 现金残差（推导值）；累计收益 = 期末资产 − 净投入。
        柱状图为每月入金 / 出金，正负分色；月份缺数据时不留空柱。
      </p>
    </template>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import VChart from "vue-echarts";
import dayjs from "dayjs";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import { getLedgerCashFlow, type LedgerCashFlow } from "@/api/summary";
import { formatAmount } from "@/utils/currency";
import { getCssVar, useThemeTick } from "@/composables/echarts/theme";

defineOptions({ name: "LedgerCashFlowCard" });

const props = defineProps<{ ledgerId: number }>();

const RANGE_OPTIONS = [
  { label: "半年", value: 180 },
  { label: "1 年", value: 365 },
  { label: "3 年", value: 1095 }
] as const;

const rangeDays = ref<(typeof RANGE_OPTIONS)[number]["value"]>(365);
const data = ref<LedgerCashFlow | null>(null);
const loadError = ref("");

const totals = computed(() => data.value?.totals ?? null);
const missingDays = computed(() => data.value?.coverage?.missing_nav_days ?? 0);

function money(value?: number | null): string {
  if (value === null || value === undefined) return "—";
  return `¥${formatAmount(value)}`;
}

async function fetchCashFlow() {
  if (!props.ledgerId) return;
  loadError.value = "";
  try {
    const res = await getLedgerCashFlow({
      ledger_id: props.ledgerId,
      start_date: dayjs().subtract(rangeDays.value, "day").format("YYYY-MM-DD")
    });
    data.value = res.data;
  } catch (e: any) {
    // 端点 400（账户不存在/跨家庭）或网络错误：如实报，不留旧图（旧图 = 假数据）
    data.value = null;
    loadError.value = e?.response?.data?.message || "资金流动数据加载失败";
    console.error("获取账户资金流动失败:", e);
  }
}

const themeTick = useThemeTick();

/** 图表颜色一律读 CSS 变量（design.md：禁止硬编码色值） */
function token(name: string, fallback: string): string {
  void themeTick.value; // 暗色切换时重算 option，触发重绘（#976）
  return getCssVar(name, fallback);
}

const lineOption = computed(() => {
  const series = data.value?.net_worth_series ?? [];
  const dates = series.map(item => item.date);
  const worth = series.map(item => item.net_worth);
  const invested = series.map(item => item.cum_net_invested);
  const axisColor = token("--text-tertiary-ink", "#8c8478");
  const splitColor = token("--border-subtle", "#f0ebe4");
  const worthColor = token("--brand-600", "#f06b57");
  const investedColor = token("--text-tertiary", "#8c8478");

  return {
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: number | null) =>
        v === null ? "—" : `¥${formatAmount(v)}`
    },
    legend: { show: false },
    grid: { left: 64, right: 16, top: 16, bottom: 28 },
    xAxis: {
      type: "category",
      data: dates,
      axisLine: { lineStyle: { color: splitColor } },
      axisLabel: { color: axisColor, hideOverlap: true },
      axisTick: { show: false }
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: {
        color: axisColor,
        formatter: (v: number) => formatAmount(v, 0)
      },
      splitLine: { lineStyle: { color: splitColor } }
    },
    series: [
      {
        name: "持仓市值",
        type: "line",
        data: worth,
        showSymbol: false,
        // 缺价日保持断线：补 0 会被读成「当天市值归零」
        connectNulls: false,
        lineStyle: { width: 2, color: worthColor },
        itemStyle: { color: worthColor }
      },
      {
        name: "累计净投入",
        type: "line",
        step: "end",
        data: invested,
        showSymbol: false,
        connectNulls: true,
        lineStyle: { width: 1.5, type: "dashed", color: investedColor },
        itemStyle: { color: investedColor }
      }
    ]
  };
});

const barOption = computed(() => {
  const monthly = data.value?.monthly ?? [];
  const months = monthly.map(item => item.month);
  const axisColor = token("--text-tertiary-ink", "#8c8478");
  const splitColor = token("--border-subtle", "#f0ebe4");
  const inColor = token("--brand-600", "#f06b57");
  const outColor = token("--color-fall", "#3f8f66");

  return {
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: number) => `¥${formatAmount(Math.abs(v))}`
    },
    legend: { show: false },
    grid: { left: 64, right: 16, top: 16, bottom: 28 },
    xAxis: {
      type: "category",
      data: months,
      axisLine: { lineStyle: { color: splitColor } },
      axisLabel: { color: axisColor, hideOverlap: true },
      axisTick: { show: false }
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: axisColor,
        formatter: (v: number) => formatAmount(v, 0)
      },
      splitLine: { lineStyle: { color: splitColor } }
    },
    series: [
      {
        name: "入金",
        type: "bar",
        stack: "flow",
        data: monthly.map(item => item.deposit),
        itemStyle: { color: inColor }
      },
      {
        name: "出金",
        type: "bar",
        stack: "flow",
        // 出金画在轴下方（负向），一眼看出「这个月是投钱还是取钱」
        data: monthly.map(item => -item.withdraw),
        itemStyle: { color: outColor }
      }
    ]
  };
});

onMounted(fetchCashFlow);
watch([() => props.ledgerId, rangeDays], fetchCashFlow);
</script>

<style scoped>
.cash-flow__metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: var(--space-standard);
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric__label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.metric__value {
  font-size: var(--text-num-strong);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 这一屏只有「净投入 / 期末资产」两个主线数字提档并上品牌墨色，
   其余两个保持默认墨色——四个数都喊等于都不喊（2026-10-19 UI 原则）。 */
.metric--key .metric__value {
  font-size: var(--text-num-hero);
}

.metric--key:first-of-type .metric__value {
  color: var(--text-primary);
}

.metric--key:last-of-type .metric__value {
  color: var(--brand-ink);
}

.cash-flow__hint,
.cash-flow__error,
.cash-flow__caliber {
  margin: 8px 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.cash-flow__error {
  color: var(--color-warning-ink);
}

.cash-flow__chart {
  margin-top: var(--space-standard);
}

.chart {
  width: 100%;
}

.chart--line {
  height: 280px;
}

.chart--bar {
  height: 200px;
}

.cash-flow__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 4px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.legend::before {
  display: inline-block;
  width: 10px;
  height: 2px;
  margin-right: 6px;
  vertical-align: middle;
  content: "";
  background: currentcolor;
}

.legend--worth {
  color: var(--brand-600, #f06b57);
}

.legend--missing {
  color: var(--color-warning-ink);
}

@media (width <= 640px) /* breakpoint-allow: 卡片内四宫格换行（内容级） */ {
  .cash-flow__metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
