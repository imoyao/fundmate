<!--
  组合页「超额走势」区块（#2685）：组合累计收益 vs 基准累计收益两条线 + 基准切换。

  口径全部由后端算好（`/summary/benchmark-excess/` 的 `series`）：
  - 组合线**末点 ≡ 上方「超额收益」卡里的组合收益率**，基准线末点 ≡ 基准同期涨跌幅
    ——分母固定，本组件不做任何 rebase / 复利连乘（前端二次计算必然与卡片对不上）；
  - 基准不可算（港美股持仓 / 未识别 / 指数覆盖不足）时只画组合线并给降级文案，
    **不画一条 0 线冒充基准**；
  - 换基准 = 改组合设置（`Portfolio.benchmark` 存指数代码）+ 重取，不引入第二份映射表。

  ## 周期筛选（#3107）

  以前写死近 90 天。现在由 `ChartRangeTabs` 提供九档（近1月…成立来），
  **受控**：区间值由父页持有并同步喂给上方指标卡——曲线末点与卡片的「超额收益」
  必须同区间，两个组件各存一份状态迟早分叉。档位含义与起止日换算全在
  `utils/chartRange.ts`，本组件不出现任何天数常量。

  ## 只画，不取数（#3112）

  数据由父页的 `usePortfolioExcess` 取一次，以 `state` 传进来。此前本组件自己
  也调 `getBenchmarkExcess()`——与卡片那次请求的端点、参数完全相同，等于每次
  切档让后端把同一个聚合算两遍（真库组合 1 近5年 3.06s + 5.80s），还因为两次
  返回时刻不同而短暂出现「卡片已是新档、曲线还是旧档」。**同一份数据只能有一个
  所有者**：容器之间靠 props 传递，不靠各取一遍再指望它们同时到达。
-->
<template>
  <CardBlock>
    <div class="excess-trend__head">
      <div>
        <h3 class="excess-trend__title">超额走势</h3>
        <p class="excess-trend__caption">{{ captionText }}</p>
      </div>
      <el-select
        :model-value="currentCode"
        class="excess-trend__select"
        placeholder="选择基准"
        :loading="benchmarksLoading"
        @update:model-value="handleSwitchBenchmark"
      >
        <el-option
          v-for="item in benchmarks"
          :key="item.code"
          :label="item.name"
          :value="item.code"
        />
      </el-select>
    </div>

    <!-- 长周期首次加载要补算历史（物化未覆盖的日期），必须给转圈——
         否则用户点了「成立来」看到的是十几秒没反应的旧图 -->
    <div v-loading="state.loading" class="excess-trend__chart">
      <p v-if="state.error" class="excess-trend__hint">
        {{ state.error }}
      </p>
      <p v-else-if="!series.length" class="excess-trend__hint">
        {{ emptyHint }}
      </p>
      <TimeSeriesChart
        v-else
        :categories="categories"
        :series="chartSeries"
        unit="%"
        :height="260"
      />
    </div>
    <!-- 周期筛选（图下方，与产品图同位置）：一排常用档 + 「更多」下拉 -->
    <div class="excess-trend__range">
      <ChartRangeTabs v-model="range" aria-label="超额走势区间" />
    </div>

    <p v-if="benchmarkHint" class="excess-trend__hint">
      {{ benchmarkHint }}
    </p>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import CardBlock from "@/components/CardBlock/index.vue";
import ChartRangeTabs from "@/components/ChartRangeTabs/index.vue";
import TimeSeriesChart, {
  type TimeSeriesItem
} from "@/components/Charts/TimeSeriesChart.vue";
import { getBenchmarks, type BenchmarkOption } from "@/api/summary";
import { updatePortfolio } from "@/api/portfolio";
import {
  CHART_RANGE_INCEPTION,
  chartRangeLabel,
  type ChartRangeKey
} from "@/utils/chartRange";
import { excessDegradHint } from "@/utils/benchmarkExcess";
import type { ExcessState } from "./portfolioDetailModel";

defineOptions({ name: "PortfolioExcessTrend" });

const props = defineProps<{
  /** 组合 id：只用于「换基准」写回设置，取数在父页（见模板上方注释） */
  portfolioId: number;
  /** 父页唯一的一次取数结果：数据 / 加载中 / 错误都从这一处来 */
  state: ExcessState;
}>();

/** 区间受控：父页与「基准 / 超额收益」两张卡共用同一个值（见模板上方注释） */
const range = defineModel<ChartRangeKey>("range", { default: "3m" });

const emit = defineEmits<{ updated: [] }>();

const benchmarks = ref<BenchmarkOption[]>([]);
const benchmarksLoading = ref(false);

const series = computed(() => props.state.data?.series ?? []);
const categories = computed(() => series.value.map(item => item.date));
const hasBenchmark = computed(() =>
  series.value.some(item => item.benchmark_cum_pct !== null)
);

/**
 * 「成立来」的实际起点提示。
 *
 * 只有这一档需要：`start_date` 回的是后端按作用域解析出的**真实起点**，可能落在
 * 无流水的 90 天兜底上，必须报出来。其余档位的 `start_date` 就是请求值（引擎不裁剪），
 * 数据撑不住时走 `range_reason` 降级，靠 `emptyHint` 说明——不在这里假装「数据自 X 起」。
 */
const actualStartHint = computed(() => {
  const data = props.state.data;
  if (!data?.start_date) return "";
  if (range.value !== CHART_RANGE_INCEPTION) return "";
  return `（自 ${data.start_date} 起）`;
});

/** 说明文案：档位标签 +（数据不够长时）实际起点 */
const captionText = computed(() => {
  const label = chartRangeLabel(range.value);
  return `${label}${actualStartHint.value}：组合累计收益 vs 基准累计收益（末点与上方卡片口径一致）`;
});

/**
 * 空图的**分级**说明：不同降级原因对应完全不同的处置动作，一句「没有可画的数据」
 * 会把「起点资产过小」读成「功能坏了」。
 *
 * 原因 → 文案的映射**只有一个出口**（`utils/benchmarkExcess::excessDegradHint`，
 * 与上方两张指标卡共用）；这里只在「换更短周期就能看」的那几档补一句动作。
 */
const SHORTER_RANGE_REASONS = new Set([
  "no_baseline",
  "baseline_not_representative"
]);

const emptyHint = computed(() => {
  const hint = excessDegradHint(props.state.data);
  if (!hint) {
    return "这段时间还没有可画的日数据（可能缺净值或基准覆盖不足）。";
  }
  const reason = props.state.data?.range_reason ?? "";
  return SHORTER_RANGE_REASONS.has(reason) ? `${hint}，换更短的周期看。` : hint;
});

/** 当前选中基准：以后端归一后的代码为准（降级时为空，让用户重选） */
const currentCode = computed(() => props.state.data?.benchmark?.code ?? "");

/**
 * 基准线不可画时的说明：把后端 reason 翻成人话，避免「怎么只有一条线」。
 * 之所以不复用卡片文案函数：卡片讲的是「数值为什么是 --」，这里讲的是「线为什么少一条」。
 */
const benchmarkHint = computed(() => {
  const bench = props.state.data?.benchmark;
  if (!bench || hasBenchmark.value) return "";
  const reason = bench.reason;
  if (reason === "unrecognized_benchmark") {
    return "当前基准无法识别（可能存的是旧值或非 A 股指数），请在上方下拉里重选。";
  }
  if (reason === "non_cn_a_holdings") {
    return "持仓含港美股，A 股宽基不代表它们，因此不画基准线（不拿沪深300 顶替）。";
  }
  if (reason) {
    return "基准在该区间内报价不足，无法画出同期曲线（不补 0、不拿别的指数顶替）。";
  }
  return "";
});

const chartSeries = computed<TimeSeriesItem[]>(() => {
  const list: TimeSeriesItem[] = [
    { name: "组合累计", data: series.value.map(item => item.scope_cum_pct) }
  ];
  if (hasBenchmark.value) {
    list.push({
      name: props.state.data?.benchmark?.name ?? "基准累计",
      data: series.value.map(item => item.benchmark_cum_pct),
      dashed: true
    });
  }
  return list;
});

async function fetchBenchmarks() {
  benchmarksLoading.value = true;
  try {
    const res = await getBenchmarks();
    benchmarks.value = res.data ?? [];
  } catch {
    // 清单拉不到不算致命：曲线照画，只是不能在这里换基准（仍可进编辑弹窗改）
    benchmarks.value = [];
  } finally {
    benchmarksLoading.value = false;
  }
}

async function handleSwitchBenchmark(code: string | number | undefined) {
  if (!code || code === currentCode.value) return;
  try {
    // #981 同款：只传要改的字段，避免把界面上没加载的字段一并写回
    await updatePortfolio(props.portfolioId, { benchmark: String(code) });
    // 数据由父页持有 ⇒ 通知它重取；本组件不自己发那次请求（否则又变两份）
    emit("updated");
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "切换基准失败");
  }
}

// 基准清单只有本组件用（下拉框），仍在此自取；曲线数据一律读 props
onMounted(fetchBenchmarks);
</script>

<style scoped>
.excess-trend__head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 8px;
}

.excess-trend__title {
  font-size: var(--text-num-strong);
  font-weight: 600;
  color: var(--text-primary);
}

.excess-trend__caption {
  margin-top: 4px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.excess-trend__select {
  flex: none;
  width: 160px;
}

/* 周期筛选独立成行（与产品图同位置）：左对齐、与图表留一道呼吸 */
.excess-trend__range {
  display: flex;
  margin-top: 10px;
}

/* loading 时也要有落脚点：空态一行字撑不起卡片，切档会让下方控件上下跳 */
.excess-trend__chart {
  min-height: 60px;
}

.excess-trend__hint {
  margin-top: 8px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
