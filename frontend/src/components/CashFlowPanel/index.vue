<!--
  「资金流动」区块（#2616 账户级 / #2681 组合级，后端 GET /api/summary/cash-flow/）。

  回答的是收益率回答不了的那个问题：「这个账户 / 组合我一共投进去多少、取出来多少、
  现在值多少、到底赚了多少」。收益率高不代表投入规模合适，只有资金流动能回答。

  三级作用域：不传 props = 不取数；`ledger-id` = 账户级；`portfolio-id` = 组合级
  （成员账本 Σ，组合内互转由后端抵消为 0）；`family` 布尔 = 家庭级（2026-11-27，
  全家庭合并，与复盘页的 XIRR / 清仓周期同口径）。三者互斥，父页自行保证
  （后端同传回 400）。

  口径纪律（docs/spec/cashflow-layers.md，禁止在本组件里改口径）：
  - 入金/出金（L1）才是资金进出；买入/卖出是账户内换形态（L2），不计入这两个数；
  - 净投入 = 入金 − 出金，恒为「自开户以来」，**切区间不会变小**；
  - 净值线是持仓市值口径，现金残差是**推导值**，单独展示、不进曲线；
  - 缺价日 `net_worth = null` 保持断线，**绝不补 0**（补 0 等于把「没数据」画成「持平」）。
-->
<template>
  <CardBlock class="cash-flow">
    <SectionHeader title="资金流动">
      <!-- 口径全部收在 ⓘ（2026-11-15）：卡片下方原有两行小字重复讲「现金残差是
           推导值」，与这里第三段同义；一并移到这里后，卡面只剩数字和两张图。
           ⚠️ 原文用 `**加粗**` 写在文本节点里——Markdown 语法在 Vue 模板中不生效，
           页面上真的显示了两对星号。改用 <strong>，「⭐」这段是 bug 修复而非改文案。 -->
      <template #info>
        <p>
          入金 / 出金只统计<strong>跨出{{ scopeWord }}</strong
          >的钱；买入、卖出是内部换形态，不算。
        </p>
        <p>净投入 = 累计入金 − 累计出金，自开户以来统计，不随时间区间变化。</p>
        <p>
          这里的净投入是<strong>出入金</strong>口径；收益概览里那张「净投入」卡是
          累计买入 − 累计卖出 / 分红（本金口径），两者不是同一个数，不能相减。
        </p>
        <p v-if="!family">
          净值线为<strong>持仓市值</strong>；现金残差
          <strong>{{ money(totals?.cash_residual) }}</strong>
          由流水推导（缺流水会偏），未计入曲线。
        </p>
        <p v-if="!family">
          期末资产 = 持仓市值 + 现金残差（推导值）；累计收益 = 期末资产 −
          净投入。
        </p>
        <p v-else>
          家庭级只报<strong>持仓市值</strong>：现金残差是账户级推导值（靠「这个集合的
          入金都记全了」才成立），家庭合并后缺一笔入金就会把资产算成负数，故不展示
          期末资产 / 累计收益——要看账户余额请到账户页。
        </p>
        <p>柱状图为每月入金 / 出金，正负分色；月份缺数据时不留空柱。</p>
      </template>
      <template #action>
        <ChartRangeTabs v-model="range" aria-label="资金流动区间" />
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
          <!-- 家庭级不给「期末资产」（= 市值 + 不可信的现金残差），改报市值本体：
               两个数都在净值线末点上，读者能对上 -->
          <span class="metric__label">{{
            family ? "持仓市值" : "期末资产"
          }}</span>
          <span class="metric__value">
            {{ money(family ? totals?.market_value : totals?.end_asset) }}
          </span>
        </div>
      </div>

      <!-- 缺入金记录：净投入恒 0，必须说清是「没录」而不是「没赚钱」 -->
      <p
        v-if="data && totals && !totals.has_deposit_record"
        class="cash-flow__hint"
      >
        {{ scopeWord }}还没有入金记录，净投入按 0
        展示——补录入金后，这里的收益才有意义。
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
        <span v-if="inceptionLabel" class="legend">
          投资起点 {{ inceptionLabel }}
        </span>
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
    </template>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import ChartRangeTabs from "@/components/ChartRangeTabs/index.vue";
import { getCssVar, useThemeTick } from "@/composables/echarts/theme";
import { formatAmount } from "@/utils/currency";
import { useCashFlow } from "./useCashFlow";

defineOptions({ name: "CashFlowPanel" });

const props = defineProps<{
  /** 账户级口径；与 portfolioId / family 互斥 */
  ledgerId?: number;
  /** 组合级口径；与 ledgerId / family 互斥 */
  portfolioId?: number;
  /** 家庭级口径（全家庭合并）；没有 id，靠这个布尔表达 */
  family?: boolean;
}>();

/** 文案口径词：账户页说「本账户」、组合页说「本组合」、复盘页说「本家庭」 */
const scopeWord = computed(() => {
  if (props.family) return "本家庭";
  return props.portfolioId != null ? "本组合" : "本账户";
});

const {
  range,
  data,
  loadError,
  totals,
  missingDays,
  inceptionLabel,
  money,
  refresh
} = useCashFlow(props);

/** 父页「刷新数据」用：本面板与其它自含取数区块同一契约（defineExpose.refresh） */
defineExpose({ refresh });

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

/* `.cash-flow__caliber` 已随脚注删除（2026-11-15，内容并入 SectionHeader ⓘ），
   选择器同步移除——留着的死类名会让下一个人以为那里还有东西。 */
.cash-flow__hint,
.cash-flow__error {
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
