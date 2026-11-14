<!--
  组合页「超额走势」区块（#2685）：组合累计收益 vs 基准累计收益两条线 + 基准切换。

  口径全部由后端算好（`/summary/benchmark-excess/` 的 `series`）：
  - 组合线**末点 ≡ 上方「超额收益」卡里的组合收益率**，基准线末点 ≡ 基准同期涨跌幅
    ——分母固定，本组件不做任何 rebase / 复利连乘（前端二次计算必然与卡片对不上）；
  - 基准不可算（港美股持仓 / 未识别 / 指数覆盖不足）时只画组合线并给降级文案，
    **不画一条 0 线冒充基准**；
  - 换基准 = 改组合设置（`Portfolio.benchmark` 存指数代码）+ 重取，不引入第二份映射表。

  ## 周期筛选（#3109）

  以前写死近 90 天。现在由 `ChartRangeTabs` 提供九档（近1月…成立来），
  **受控**：区间值由父页持有并同步喂给上方指标卡——曲线末点与卡片的「超额收益」
  必须同区间，两个组件各存一份状态迟早分叉。档位含义与起止日换算全在
  `utils/chartRange.ts`，本组件不出现任何天数常量。
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

    <p v-if="loadError" class="excess-trend__hint">
      {{ loadError }}
    </p>
    <p v-else-if="!series.length" class="excess-trend__hint">
      这段时间还没有可画的日数据（可能缺净值或基准覆盖不足）。
    </p>
    <TimeSeriesChart
      v-else
      :categories="categories"
      :series="chartSeries"
      unit="%"
      :height="260"
    />

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
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import CardBlock from "@/components/CardBlock/index.vue";
import ChartRangeTabs from "@/components/ChartRangeTabs/index.vue";
import TimeSeriesChart, {
  type TimeSeriesItem
} from "@/components/Charts/TimeSeriesChart.vue";
import {
  getBenchmarkExcess,
  getBenchmarks,
  type BenchmarkExcessResult,
  type BenchmarkOption
} from "@/api/summary";
import { updatePortfolio } from "@/api/portfolio";
import {
  CHART_RANGE_INCEPTION,
  chartRangeLabel,
  chartRangeParams,
  type ChartRangeKey
} from "@/utils/chartRange";

defineOptions({ name: "PortfolioExcessTrend" });

const props = defineProps<{
  /** 组合 id：曲线与基准设置都按它取数 */
  portfolioId: number;
}>();

/** 区间受控：父页与「基准 / 超额收益」两张卡共用同一个值（见模板上方注释） */
const range = defineModel<ChartRangeKey>("range", { default: "3m" });

const emit = defineEmits<{ updated: [] }>();

const excess = ref<BenchmarkExcessResult | null>(null);
const benchmarks = ref<BenchmarkOption[]>([]);
const benchmarksLoading = ref(false);
const loadError = ref("");

const series = computed(() => excess.value?.series ?? []);
const categories = computed(() => series.value.map(item => item.date));
const hasBenchmark = computed(() =>
  series.value.some(item => item.benchmark_cum_pct !== null)
);

/**
 * 数据不够长时的实际起点提示（「近5年」在只运行一年的组合上只画得出一年的线）。
 *
 * 「成立来」不提示：后端解析出的起点本身就是真实起点，没有「比请求更短」这回事。
 */
const actualStartHint = computed(() => {
  const data = excess.value;
  if (!data?.start_date) return "";
  const requested = chartRangeParams(range.value).start_date;
  if (requested === CHART_RANGE_INCEPTION) return "";
  // YYYY-MM-DD 的字典序即时间序，无需再解析成 Date 比较
  return data.start_date > requested ? `（数据自 ${data.start_date} 起）` : "";
});

/** 说明文案：档位标签 +（数据不够长时）实际起点 */
const captionText = computed(() => {
  const label = chartRangeLabel(range.value);
  return `${label}${actualStartHint.value}：组合累计收益 vs 基准累计收益（末点与上方卡片口径一致）`;
});

/** 当前选中基准：以后端归一后的代码为准（降级时为空，让用户重选） */
const currentCode = computed(() => excess.value?.benchmark?.code ?? "");

/**
 * 基准线不可画时的说明：把后端 reason 翻成人话，避免「怎么只有一条线」。
 * 之所以不复用卡片文案函数：卡片讲的是「数值为什么是 --」，这里讲的是「线为什么少一条」。
 */
const benchmarkHint = computed(() => {
  const bench = excess.value?.benchmark;
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
      name: excess.value?.benchmark?.name ?? "基准累计",
      data: series.value.map(item => item.benchmark_cum_pct),
      dashed: true
    });
  }
  return list;
});

async function fetchExcess() {
  loadError.value = "";
  try {
    const res = await getBenchmarkExcess({
      ...chartRangeParams(range.value),
      portfolio_id: props.portfolioId
    });
    excess.value = res.data;
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    excess.value = null;
    loadError.value = err?.response?.data?.message || "超额走势加载失败";
  }
}

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
    await fetchExcess();
    // 上方「基准指数 / 超额收益」两张卡来自同一个接口，必须一起刷新
    emit("updated");
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "切换基准失败");
  }
}

onMounted(async () => {
  await Promise.all([fetchExcess(), fetchBenchmarks()]);
});

watch(() => props.portfolioId, fetchExcess);
// 切档即重取：range 由父页与「超额收益」卡共用，两边不可能各自停在一段区间
watch(range, fetchExcess);
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

.excess-trend__hint {
  margin-top: 8px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
