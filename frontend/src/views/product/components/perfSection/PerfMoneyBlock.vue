<script setup lang="ts">
import { computed } from "vue";
import type { FundPerformanceResult } from "@/api/products";
import { formatPrice } from "@/utils/pricePrecision";
import { DASH, fmtPct } from "./perfFormat";
import { buildBenchmarkRows, buildPeerRows, hasAnyValue } from "./perfRows";
import PerfFactGrid from "./PerfFactGrid.vue";

/**
 * 货币基金分支（#980 拆分）。
 *
 * 货币基金没有日涨跌 / 回撤口径，后端改返万份收益 + 七日年化，本段只显这两项，
 * 不显净值型指标——避免误读「货币也跌了」。
 *
 * 同类分位与基准相对仍适用：绝对值跨类别不可比，但「在同类里排第几」可跨类读。
 */
const props = defineProps<{
  perf: FundPerformanceResult;
}>();

const peerRows = computed(() => buildPeerRows(props.perf));
const benchmarkRows = computed(() => buildBenchmarkRows(props.perf));
const hasBenchmarkRows = computed(() => hasAnyValue(benchmarkRows.value));

/**
 * 万份收益：货币基金按净值口径 4 位小数。
 *
 * 走 `formatPrice(v, "money_fund")` 而不是本地 `toFixed(4)`——金额精度只有一处真源
 * （`utils/pricePrecision.ts`），拆组件时顺手把这里从守卫基线里摘掉了。
 * 缺失仍降级「—」而不是「— 元」：单位挂在一个空占位上会读成「0 元」。
 */
const navPer10kText = computed(() =>
  props.perf.nav_per_10k == null
    ? DASH
    : `${formatPrice(props.perf.nav_per_10k, "money_fund")} 元`
);
</script>

<template>
  <dl class="performance-section__kpi">
    <div class="performance-section__kpi-item">
      <dt class="performance-section__label">七日年化</dt>
      <dd class="performance-section__value">
        {{ fmtPct(perf.annual_return_7d) }}
      </dd>
    </div>
    <div class="performance-section__kpi-item">
      <dt class="performance-section__label">万份收益</dt>
      <dd class="performance-section__value">
        {{ navPer10kText }}
      </dd>
    </div>
  </dl>
  <!-- 同类内分位（#167）：绝对值跨类别不可比，分位可跨类读 -->
  <template v-if="peerRows.length">
    <div class="performance-section__block-label">
      同类分位
      <span class="performance-section__aside">同类内排位，越大越靠前</span>
    </div>
    <PerfFactGrid :items="peerRows" />
  </template>

  <!-- 基准相对（#167）：债基对债指数、股基对同类股基指数——按类型映射，不解析自然语言 -->
  <template v-if="perf.benchmark">
    <div class="performance-section__block-label">
      对比基准
      <span class="performance-section__aside">{{ perf.benchmark.name }}</span>
    </div>
    <PerfFactGrid
      v-if="perf.benchmark.available && hasBenchmarkRows"
      :items="benchmarkRows"
    />
    <!-- 基准选定但序列缺：显式说明，不退回沪深300 顶替（那会让用户读不到「没比过」） -->
    <p v-else class="section-footnote">
      {{ perf.benchmark.reason || "基准数据暂不可用" }}
    </p>
    <p class="section-footnote">
      基准按基金类型映射（{{ perf.benchmark.matched_by }}）
      <template v-if="perf.benchmark.sample_points">
        · 共同交易日 {{ perf.benchmark.sample_points }} 天</template
      >
    </p>
  </template>

  <p class="section-footnote">
    数据来源：{{ perf.source
    }}<template v-if="perf.as_of"> · 截至 {{ perf.as_of }}</template>
    <template v-if="perf.samples != null">
      · 七日年化 = 近 {{ perf.window_days ?? 7 }} 个自然日内
      {{ perf.samples }} 个已发布样本的日均值 × 365
      <template v-if="perf.samples < (perf.window_days ?? 7)">
        （不足 {{ perf.window_days ?? 7 }} 天，含节假日缺口）
      </template>
    </template>
    · 货币基金（万份收益 / 七日年化，无回撤口径）
  </p>
</template>
