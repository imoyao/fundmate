<script setup lang="ts">
import { computed } from "vue";
import type { FundPerformanceResult } from "@/api/products";
import { PERIOD_LABEL, daysText, drawdownText, fmtPct } from "./perfFormat";
import { buildRiskRows, hasAnyValue, type PerfFactItem } from "./perfRows";
import PerfFactGrid from "./PerfFactGrid.vue";

/**
 * 场外基金分支（#980 拆分）：区间收益 + 回撤 + 风险比 + 脚注。
 *
 * 三个「回撤」的读法在这里最容易被改错，故把口径写死在构造里：
 * - **本轮回撤**（`current_drawdown`）是「现在疼不疼」，**最大回撤**是「最疼过多少」——
 *   两个都要显。只显最大值会把「跌 30% 但已修复」与「跌 30% 且仍在水下」显示成一个数，
 *   而后一种正是要警惕的「跌起来比涨得还猛」（#167 用户原话）。
 * - 风险比只在同类内可比（债基波动天生小、夏普系统性偏高），故不画排行榜、不给好坏色。
 * - rf 与窗口随值下发并展示在脚注——不告诉用户 rf 取多少的夏普不可复核。
 */
const props = defineProps<{
  perf: FundPerformanceResult;
}>();

const intervalRows = computed<PerfFactItem[]>(() =>
  (props.perf.intervals || []).map(iv => ({
    key: iv.key,
    label: iv.label,
    num: iv.value
  }))
);

const drawdownRows = computed<PerfFactItem[]>(() => {
  const p = props.perf;
  return [
    {
      key: "current",
      label: "本轮回撤",
      value: drawdownText(p.current_drawdown),
      // 「已 N 天」只在有高点日期时才有意义：没有起点就谈不上熬了多久
      sub: p.current_drawdown_peak_date
        ? `高点 ${p.current_drawdown_peak_date} · 已 ${daysText(
            p.current_drawdown_days
          )}`
        : undefined
    },
    {
      key: "max",
      label: `最大回撤（${p.max_drawdown_window || p.risk_window || "近3年"}）`,
      value: fmtPct(p.max_drawdown),
      sub:
        p.max_drawdown_peak_date && p.max_drawdown_trough_date
          ? `${p.max_drawdown_peak_date} → ${p.max_drawdown_trough_date}`
          : undefined
    },
    {
      key: "vol",
      label: "年化波动率（近1年）",
      value: fmtPct(p.volatility_1y)
    }
  ];
});

/** 风险比 + 胜率：胜率排在最后，它是「体验」不是「风险调整后收益」 */
const riskRows = computed<PerfFactItem[]>(() => {
  const p = props.perf;
  const period = PERIOD_LABEL[p.win_rate_period || "month"] || "月";
  return [
    ...buildRiskRows(p),
    {
      key: "win_rate",
      label: `胜率（${period}）`,
      hint: `${PERIOD_LABEL[p.win_rate_period || "month"] || ""}频；滚动窗口重叠，是持有体验而非概率`,
      value: fmtPct(p.win_rate)
    }
  ];
});

const hasRiskRows = computed(() => hasAnyValue(buildRiskRows(props.perf)));
</script>

<template>
  <div class="performance-section__block-label">区间收益</div>
  <PerfFactGrid :items="intervalRows" />

  <div class="performance-section__block-label">回撤</div>
  <PerfFactGrid :items="drawdownRows" />

  <!-- 风险比（#167）：只摆数字与口径，不给排序、不着色 —— 跨类别不可比 -->
  <template v-if="hasRiskRows">
    <div class="performance-section__block-label">
      风险比
      <span class="performance-section__aside"
        >{{ perf.risk_window || "近3年" }} · 同类内可比</span
      >
    </div>
    <PerfFactGrid :items="riskRows" />
  </template>

  <p class="section-footnote">
    数据来源：{{ perf.source
    }}<template v-if="perf.as_of"> · 截至 {{ perf.as_of }}</template>
    <template v-if="perf.risk_free_rate != null">
      · 无风险利率
      {{
        (perf.risk_free_rate * 100).toFixed(2)
      }}%（一年期国债收益率近似，用于夏普等指标）</template
    >
    <template v-if="perf.risk_sample_points">
      · 样本 {{ perf.risk_sample_points }} 个净值点</template
    >
    <template v-if="perf.acc_nav_caveat"> · {{ perf.acc_nav_caveat }}</template>
  </p>
  <!-- 口径告警（如检出净值跳变）：与「不可复核的数字」相比，宁可显式说出来 -->
  <p
    v-for="(caveat, i) in perf.risk_caveats || []"
    :key="i"
    class="performance-section__caveat"
  >
    {{ caveat }}
  </p>
</template>
