<script setup lang="ts">
import { computed, ref } from "vue";
import VChart from "vue-echarts";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import {
  CHART_FALLBACKS,
  CHART_TOKENS,
  getCssVar,
  useThemeTick
} from "@/composables/echarts/theme";
import type { TradeTimelineResult } from "@/api/products";

/**
 * 累计收益面板（#2171 P1 · 走势卡内第二面板）。
 *
 * 口径（与后端 `services/trade_timeline.py` 同一真相源，前端只排版）：
 * - **累计已实现盈亏** = 现金分红 + 净回款（卖出/取出金额−费）− 释放成本；
 *   **不做市值估计**——浮动盈亏在「我的持仓」卡（unit_nav 口径，NavService 标准
 *   口径），同页不造第二个收益数字（#2171 决策）；
 * - **收益率 = 累计已实现 ÷ 累计投入**（简单回报率，非年化）：年化数字在业绩卡
 *   XIRR，不重复造；
 * - 曲线**全程展示、不随走势区间缩放**：它是「至今累计」，随区间裁剪会丢掉
 *   早期的落袋（区间是看净值波动的窗口，不是看盈亏历史的窗口）；
 * - 无流水 / 未登录（timeline 为空结构）时整块不渲染——父级据 summary 计数判断。
 */

const props = defineProps<{
  timeline: TradeTimelineResult | null;
}>();

type ProfitMode = "amount" | "rate";

const MODE_OPTIONS: { label: string; value: ProfitMode }[] = [
  { label: "金额", value: "amount" },
  { label: "收益率", value: "rate" }
];

const mode = ref<ProfitMode>("amount");
const themeTick = useThemeTick();

const summary = computed(() => props.timeline?.summary ?? null);
const profitLine = computed(() => props.timeline?.profit_line ?? []);

/** 至少两个点才成曲线（单日一笔画出来是一个点，统计条已覆盖） */
const hasCurve = computed(() => profitLine.value.length >= 2);

/** 收益率序列：累计已实现 ÷ 累计投入 × 100；投入为 0 的点留空（不编造 0%） */
const rateSeries = computed(() =>
  profitLine.value.map(p =>
    p.invested_yuan > 0
      ? +((p.realized_yuan / p.invested_yuan) * 100).toFixed(2)
      : null
  )
);

/** 已落袋 = 卖出回款 + 现金分红（真金白银回到手里的部分） */
const cashedOut = computed(
  () =>
    (summary.value?.total_sell_amount_yuan ?? 0) +
    (summary.value?.total_dividend_yuan ?? 0)
);

const chartOption = computed(() => {
  void themeTick.value; // 主题切换时重算，让曲线重读 CSS 变量
  const rise = getCssVar(CHART_TOKENS.rise, CHART_FALLBACKS.rise);
  const fall = getCssVar(CHART_TOKENS.fall, CHART_FALLBACKS.fall);
  // 盈亏曲线按**末值正负**定色：赚=红、亏=绿（A 股习惯），与涨跌语义一致
  const last = profitLine.value[profitLine.value.length - 1];
  const positive = (last?.realized_yuan ?? 0) >= 0;
  const lineColor = positive ? rise : fall;
  const splitLine = {
    lineStyle: {
      color: getCssVar(CHART_TOKENS.borderLight, CHART_FALLBACKS.borderLight)
    }
  };
  const isRate = mode.value === "rate";
  const data = isRate
    ? rateSeries.value
    : profitLine.value.map(p => p.realized_yuan);

  return {
    animation: false,
    tooltip: {
      trigger: "axis",
      formatter: (params: Array<Record<string, unknown>>) => {
        if (!params?.length) return "";
        const date = String(params[0].axisValue ?? "");
        const p = params[0];
        const v = p.value;
        if (isRate) {
          const shown =
            typeof v === "number" && Number.isFinite(v) ? v.toFixed(2) : "—";
          return `<b>${date}</b><br/>累计收益率：${shown}%`;
        }
        const shown =
          typeof v === "number" && Number.isFinite(v) ? v.toFixed(2) : "—";
        return `<b>${date}</b><br/>累计已实现：¥${shown}`;
      }
    },
    grid: { left: 52, right: 16, top: 12, bottom: 24 },
    xAxis: {
      type: "category",
      data: profitLine.value.map(p => p.date),
      boundaryGap: false,
      axisLabel: { fontSize: 11, hideOverlap: true }
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { fontSize: 11 },
      splitLine
    },
    series: [
      {
        name: isRate ? "累计收益率" : "累计已实现",
        type: "line",
        data,
        smooth: false,
        symbol: "none",
        lineStyle: { color: lineColor, width: 2 },
        areaStyle: { color: hexToRgba(lineColor, 0.08) },
        // 零轴：盈亏曲线的正负分界，没有它「亏了多少」没有参照
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: {
            color: getCssVar(
              CHART_TOKENS.borderLight,
              CHART_FALLBACKS.borderLight
            )
          },
          label: { show: false },
          data: [{ yAxis: 0 }]
        }
      }
    ]
  };
});

/** hex → rgba：面积渐变需要具体色值（CSS 变量不能直接给 alpha） */
function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || "").trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
</script>

<template>
  <section v-if="summary" class="profit-panel">
    <div class="profit-panel__head">
      <span class="profit-panel__title">累计收益</span>
      <SegmentedControl
        v-model="mode"
        :options="MODE_OPTIONS"
        size="small"
        aria-label="切换累计收益展示口径"
      />
    </div>

    <!-- 紧凑统计条：买卖次数 + 投入 / 落袋 / 已实现（全部来自时间线汇总，
         单一真相源；浮动盈亏不在这里重复，见组件头注释） -->
    <div class="profit-panel__stats">
      <span class="profit-panel__stat">
        买入 {{ summary.buy_count }} 次 · 卖出 {{ summary.sell_count }} 次 ·
        分红 {{ summary.dividend_count }} 次
      </span>
      <span class="profit-panel__stat">
        累计投入 ¥{{ summary.total_invested_yuan.toFixed(2) }}（含费）
      </span>
      <span class="profit-panel__stat">已落袋 ¥{{ cashedOut.toFixed(2) }}</span>
      <span class="profit-panel__stat">
        已实现
        <MoneyDisplay
          :value="summary.realized_pnl_yuan"
          :decimals="2"
          :show-sign="true"
        />
      </span>
    </div>

    <v-chart
      v-if="hasCurve"
      :option="chartOption"
      :autoresize="true"
      class="profit-panel__chart"
    />

    <p class="profit-panel__footnote">
      累计已实现 = 分红 + 落袋 −
      释放成本，不含浮动盈亏（浮动见「我的持仓」）；{{
        mode === "rate"
          ? "收益率 = 累计已实现 ÷ 累计投入，非年化（年化见业绩卡）"
          : "金额模式"
      }}
    </p>
  </section>
</template>

<style scoped>
.profit-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-light);
}

.profit-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.profit-panel__title {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}

.profit-panel__stats {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.profit-panel__stat {
  font-variant-numeric: tabular-nums;
}

.profit-panel__chart {
  width: 100%;
  height: 140px;
}

.profit-panel__footnote {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}
</style>
