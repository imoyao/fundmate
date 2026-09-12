<!-- frontend/src/views/explore/components/TemperatureTrendChart.vue -->
<!--
  综合温度趋势图（2026-09-12 从 ExploreDetailPanel 抽出，见 #980「第四步：抽无状态子组件」）。
  自带标题栏 + 周期切换 + 图表，调用方只需一行 <TemperatureTrendChart />。
  抽出前该图表（约 130 行 option + 取数）内联在页面里，让页面主文件无法回到「只做编排」。
-->
<template>
  <section class="chart-section">
    <SectionHeader title="综合温度趋势">
      <template #action>
        <el-radio-group v-model="historyDays" size="small">
          <el-radio-button :value="30">30天</el-radio-button>
          <el-radio-button :value="90">90天</el-radio-button>
          <el-radio-button :value="180">半年</el-radio-button>
        </el-radio-group>
      </template>
    </SectionHeader>
    <div class="chart-wrapper">
      <v-chart
        ref="chartRef"
        :option="chartOption"
        :autoresize="true"
        style="width: 100%; height: 300px"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import VChart from "vue-echarts";
import { getTemperatureHistory } from "@/api/temperature";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getCssVar } from "@/composables/echarts/theme";

defineOptions({
  name: "TemperatureTrendChart"
});

/**
 * 温度三色：动态读取全局 token（src/style/colors.css 的 --temp-*），
 * 用 computed 实时读取，暗色切换时 CSS 变量变化可正确重读。
 * 红线（design.md）：图表颜色禁止硬编码。
 */
function readTempColorVar(name: string): string {
  return getCssVar(name, "#888");
}

const TEMP_COLORS = computed(() => ({
  low: readTempColorVar("--temp-low"),
  mid: readTempColorVar("--temp-mid"),
  high: readTempColorVar("--temp-high")
}));

/** 图表渐变需要具体色值：把 CSS 变量读出的 hex 转 rgba（透明度按原视觉保留） */
function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

const historyData = ref<{
  dates: string[];
  values: (number | null)[];
  levels?: string[];
}>({ dates: [], values: [] });
const historyDays = ref(90);
const chartRef = ref<any>(null);

const fetchHistory = async () => {
  try {
    const res = await getTemperatureHistory(historyDays.value);
    historyData.value = res.data;
  } catch (e) {
    console.error("获取历史趋势失败:", e);
  }
};

const chartOption = computed(() => {
  const dates = historyData.value.dates || [];
  const values = historyData.value.values || [];
  const levels = historyData.value.levels || [];

  // 计算颜色：根据 level 决定（复用 TEMP_COLORS，与全局 token 一致）
  const colors = levels.map(level => {
    if (level === "偏低" || level === "低估") return TEMP_COLORS.value.low;
    if (level === "偏高" || level === "高估") return TEMP_COLORS.value.high;
    return TEMP_COLORS.value.mid;
  });

  return {
    tooltip: {
      trigger: "axis",
      formatter: (params: any) => {
        const p = params[0];
        const idx = p.dataIndex;
        const level = levels[idx] || "";
        return `${p.axisValue}<br/>综合温度: ${p.value}°<br/>等级: ${level}`;
      }
    },
    grid: {
      left: 50,
      right: 20,
      top: 20,
      bottom: 30
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: {
        rotate: 30,
        fontSize: 11
      }
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      splitLine: {
        lineStyle: { color: "var(--border-light)", type: "dashed" }
      },
      axisLabel: {
        formatter: "{value}°",
        fontSize: 11
      }
    },
    series: [
      {
        name: "综合温度",
        type: "line",
        data: values,
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: {
          color: "var(--brand-700)",
          width: 2
        },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              {
                offset: 0,
                color: hexToRgba(getCssVar("--color-rise", "#e34f38"), 0.3)
              },
              {
                offset: 1,
                color: hexToRgba(getCssVar("--color-rise", "#e34f38"), 0.05)
              }
            ]
          }
        },
        itemStyle: {
          color: (params: any) => {
            const idx = params.dataIndex;
            return colors[idx] || "var(--brand-700)";
          }
        },
        markLine: {
          silent: true,
          data: [
            {
              yAxis: 70,
              label: {
                formatter: "偏高",
                color: "var(--text-tertiary)",
                fontSize: 11
              }
            },
            {
              yAxis: 40,
              label: {
                formatter: "适中",
                color: "var(--text-tertiary)",
                fontSize: 11
              }
            },
            {
              yAxis: 25,
              label: {
                formatter: "偏低",
                color: "var(--text-tertiary)",
                fontSize: 11
              }
            }
          ],
          lineStyle: {
            color: "var(--border-default)",
            type: "dashed",
            width: 1
          }
        }
      }
    ]
  };
});

onMounted(fetchHistory);

// 单一触发点：原实现同时挂了 watch 与 el-radio-group 的 @change，
// 改一次天数会连发两次请求，此处只保留 watch。
watch(historyDays, fetchHistory);
</script>

<style lang="scss" scoped>
.chart-section {
  padding: 20px 24px;
  margin-bottom: 24px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.chart-wrapper {
  width: 100%;
  height: 300px;
}
</style>
