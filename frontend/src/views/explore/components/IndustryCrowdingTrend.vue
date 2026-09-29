<!-- frontend/src/views/explore/components/IndustryCrowdingTrend.vue -->
<!--
  行业 / 赛道拥挤度趋势（#1431）：CardBlock + SectionHeader + ECharts 折线。
  · 历史序列由后端代理 + 缓存提供（**不落库**，源见 #1502，不对外暴露来源）；
  · 图表颜色一律读全局 token（design.md 红线：图表颜色禁止硬编码），多序列取 --chart-* 分类色板；
  · 接口不可用 → 显示提示（role="status"），不报错、不影响其它区块。
-->
<template>
  <CardBlock class="crowding-trend">
    <SectionHeader title="拥挤度趋势" :info="infoText">
      <template #action>
        <el-select v-model="indicator" size="small" class="trend-select">
          <el-option
            v-for="opt in INDICATOR_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-radio-group v-model="freq" size="small">
          <el-radio-button value="weekly">周度</el-radio-button>
          <el-radio-button value="monthly">月度</el-radio-button>
        </el-radio-group>
      </template>
    </SectionHeader>

    <!-- 接口不可用 / 无数据：提示而非报错 -->
    <div v-if="!loading && !hasData" class="trend-empty" role="status">
      <IconifyIconOffline icon="ep:info-filled" class="trend-empty__icon" />
      <span>{{ notice }}</span>
    </div>

    <div v-else v-loading="loading" class="trend-chart">
      <v-chart
        ref="chartRef"
        :option="chartOption"
        autoresize
        class="trend-chart__canvas"
      />
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import VChart from "vue-echarts";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  getCrowdingHistory,
  type CrowdingHistoryResponse
} from "@/api/temperature";
import { getCssVar, useThemeTick } from "@/composables/echarts/theme";

defineOptions({ name: "IndustryCrowdingTrend" });

const props = withDefaults(defineProps<{ category?: "sw" | "track" }>(), {
  category: "sw"
});

/** 图例默认勾选的序列数（31 条线全开会糊成一团）；其余序列保留在图例中，用户可随时点选 */
const TREND_DEFAULT_N = 8;

const INDICATOR_OPTIONS = [
  { value: "crowding", label: "综合拥挤度" },
  { value: "turnover_ratio", label: "成交额占比" },
  { value: "turnover_rate", label: "换手率" },
  { value: "ma60_ratio", label: "60线上占比" },
  { value: "high60_ratio", label: "新高占比" },
  { value: "margin_ratio", label: "融资买入占比" },
  { value: "big_order", label: "百万大单" }
];

const indicator = ref("crowding");
const freq = ref("weekly");
const loading = ref(false);
const chartRef = ref<any>(null);
const history = ref<CrowdingHistoryResponse["data"]>(null);
const notice = ref("");

const hasData = computed(() => Boolean(history.value?.items?.length));

const infoText = computed(
  () =>
    `按${
      props.category === "track" ? "热门赛道" : "申万一级行业"
    }展示所选指标的历史序列（周度 / 月度）。为保证可读性，默认展示最新值前 ${TREND_DEFAULT_N} 项，其余序列可在图例中点选。`
);

/** 取数组末尾第一个非空值（用于排序挑选 Top N） */
function lastNumber(values: (number | null)[]): number | null {
  for (let i = values.length - 1; i >= 0; i -= 1) {
    if (values[i] != null) return values[i] as number;
  }
  return null;
}

/** 全部序列（按最新值降序）；不截断——默认可见性交给 legendSelected 控制 */
const trendSeries = computed(() => {
  const items = history.value?.items || [];
  return items
    .filter(i => Array.isArray(i.values) && i.values.some(v => v != null))
    .map(i => ({ name: i.name, values: i.values, last: lastNumber(i.values) }))
    .filter(i => i.last != null)
    .sort((a, b) => (b.last as number) - (a.last as number))
    .map(({ name, values }) => ({ name, values }));
});

/** 图例默认勾选：仅最新值前 N 条可见，其余由用户按需开启 */
const legendSelected = computed(() => {
  const selected: Record<string, boolean> = {};
  trendSeries.value.forEach((s, i) => {
    selected[s.name] = i < TREND_DEFAULT_N;
  });
  return selected;
});

const fetchTrend = async () => {
  loading.value = true;
  try {
    const res = await getCrowdingHistory({
      category: props.category,
      indicator: indicator.value,
      freq: freq.value
    });
    // http 封装已解包 axios：res 即后端返回体 { data, message }
    if (res.data) {
      history.value = res.data;
      notice.value = "";
    } else {
      history.value = null;
      notice.value = "拥挤度趋势暂不可用，稍后自动恢复";
    }
  } catch (e) {
    console.error("获取拥挤度趋势失败:", e);
    history.value = null;
    notice.value = "拥挤度趋势暂不可用，请稍后重试";
  } finally {
    loading.value = false;
  }
};

/**
 * 折线配色：取全局图表分类色板（`--chart-01`…`--chart-08`，见 colors.css）。
 *
 * WHY 不用品牌色阶：品牌色是**单一珊瑚红色相**的深浅档，多条线叠在一起色相相同、
 * 只靠明度区分，辨识度极低；`--chart-*` 是现成的分类色板，色相各异，多序列对比更清晰。
 * （design.md 红线：图表颜色不得硬编码，必须读全局 token。）
 */
const CHART_TOKENS = [
  "--chart-01",
  "--chart-02",
  "--chart-03",
  "--chart-04",
  "--chart-05",
  "--chart-06",
  "--chart-07",
  "--chart-08"
];

const themeTick = useThemeTick();
const chartOption = computed(() => {
  void themeTick.value; // 主题切换时重算 option，触发 vue-echarts 重绘（#976）
  const dates = history.value?.dates || [];
  const series = trendSeries.value;
  const lineColors = CHART_TOKENS.map(t => getCssVar(t, "#9aa4b2"));
  const axisLabelColor = getCssVar("--text-tertiary", "#999");
  const splitLineColor = getCssVar("--border-subtle", "#f0f0f0");
  const legendColor = getCssVar("--text-secondary", "#666");

  return {
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: number | null) =>
        v == null ? "--" : Number(v).toFixed(1)
    },
    legend: {
      type: "scroll",
      bottom: 0,
      icon: "roundRect",
      itemWidth: 10,
      itemHeight: 10,
      selected: legendSelected.value,
      textStyle: { fontSize: 11, color: legendColor }
    },
    grid: { top: 16, left: 8, right: 16, bottom: 46, containLabel: true },
    xAxis: {
      type: "category",
      data: dates.map(d => String(d).slice(5)),
      axisLabel: { fontSize: 11, color: axisLabelColor },
      axisTick: { show: false }
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { fontSize: 11, color: axisLabelColor },
      splitLine: { lineStyle: { color: splitLineColor } }
    },
    series: series.map((s, i) => ({
      name: s.name,
      type: "line",
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 2, color: lineColors[i % lineColors.length] },
      itemStyle: { color: lineColors[i % lineColors.length] },
      data: s.values
    }))
  };
});

onMounted(fetchTrend);

// 单一触发点：指标 / 周期 / 分类变化时重新取数（与 TemperatureTrendChart 同约定，避免双请求）
watch([indicator, freq, () => props.category], fetchTrend);
</script>

<style lang="scss" scoped>
/* 卡片外观由 CardBlock 统一提供（docs/design/components.md「CardBlock」），此处只留外边距 */
.crowding-trend {
  margin-bottom: 24px;
}

.trend-select {
  width: 148px;
  margin-right: 12px;
}

.trend-chart {
  height: 300px;
}

.trend-chart__canvas {
  width: 100%;
  height: 100%;
}

/* 趋势不可用提示（与分区提示条同一视觉语言：提示而非报错） */
.trend-empty {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 6px 12px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--brand-400) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--brand-400) 30%, transparent);
  border-radius: 8px;
}

.trend-empty__icon {
  flex-shrink: 0;
  margin-top: 2px;
}
</style>
