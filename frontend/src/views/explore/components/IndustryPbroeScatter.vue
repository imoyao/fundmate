<!-- frontend/src/views/explore/components/IndustryPbroeScatter.vue -->
<!--
  行业 PB-ROE 散点（#2481 · 韭圈儿 pbroe-sg2，免登录，日频快照读库即回）。

  口径（契约留档 docs/working-notes/industry-pbroe-api-contract-2026-10-21.md）：
  · x = ROE(%) TTM，**可负**——负盈利行业（如房地产实测 -16.78）在 PB-ROE
    模型下有效，x 轴不得从 0 起（scale: true），并画 ROE=0 参考线帮助读图；
  · y = PB（最新）；
  · update_time 是上游数据日期，区块脚注原样标注「数据更新至 X」，不伪装实时；
  · 无快照（job 失败日 / 从未成功）→ data: null，显示「暂无数据」提示而非报错。

  配色：design.md 红线——图表颜色一律读 CSS 语义变量（ECharts 不解析 var()），
  暗色切换靠 themeTick 重算 option（#976）。上游自带 color/bg 不透出（前端令牌自治）。
-->
<template>
  <CardBlock class="pbroe-scatter">
    <SectionHeader title="行业 PB-ROE" :info="infoText">
      <template #action>
        <span v-if="updatedText" class="pbroe-scatter__updated">
          更新：{{ updatedText }}
        </span>
      </template>
    </SectionHeader>

    <!-- 接口不可用 / 无快照：提示而非报错（role="status" 供读屏播报） -->
    <div v-if="!loading && !hasData" class="pbroe-scatter__empty" role="status">
      <IconifyIconOffline
        icon="ep:info-filled"
        class="pbroe-scatter__empty-icon"
      />
      <span>{{ notice }}</span>
    </div>

    <div v-else v-loading="loading" class="pbroe-scatter__chart">
      <v-chart
        ref="chartRef"
        :option="chartOption"
        autoresize
        class="pbroe-scatter__canvas"
      />
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import VChart from "vue-echarts";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  getIndustryPbroe,
  type IndustryPbroeData,
  type IndustryPbroePoint
} from "@/api/market";
import { getCssVar, useThemeTick } from "@/composables/echarts/theme";
import { toScatterPoints, hasScatterPoints } from "./pbroeChartMetrics";

defineOptions({ name: "IndustryPbroeScatter" });

const loading = ref(false);
const chartRef = ref<any>(null);
const data = ref<IndustryPbroeData | null>(null);
const notice = ref("");

const infoText =
  "以 ROE（TTM，%）为横轴、PB 为纵轴展示申万一级行业分布。负 ROE 行业在 PB-ROE 模型下有效，不做剔除。数据来源：韭圈儿";

/** 过滤后的有效点（负 ROE 保留；NaN 点防御见 pbroeChartMetrics） */
const points = computed(() => toScatterPoints(data.value?.series));

const hasData = computed(() => hasScatterPoints(data.value?.series));

/** 区块右上角「更新：上游数据日期」——原样透出 update_time，不伪装实时 */
const updatedText = computed(() => data.value?.update_time || "");

const themeTick = useThemeTick();
const chartOption = computed(() => {
  void themeTick.value; // 主题切换时重算 option，触发 vue-echarts 重绘（#976）
  const pointColor = getCssVar("--brand-700", "#e34f38");
  const axisLabelColor = getCssVar("--text-tertiary", "#8c8478");
  const splitLineColor = getCssVar("--border-subtle", "#f0ebe4");
  const axisNameColor = getCssVar("--text-secondary", "#6b655c");
  const tooltipBg = getCssVar("--bg-card", "#ffffff");
  const tooltipText = getCssVar("--text-primary", "#2d2a24");

  return {
    tooltip: {
      trigger: "item",
      backgroundColor: tooltipBg,
      borderColor: splitLineColor,
      textStyle: { color: tooltipText, fontSize: 12 },
      formatter: (p: { data?: IndustryPbroePoint }) => {
        const d = p.data;
        if (!d) return "";
        return `<b>${d.industry}</b><br/>ROE(TTM)：${d.roe}%<br/>PB：${d.pb}`;
      }
    },
    grid: { top: 24, left: 8, right: 20, bottom: 36, containLabel: true },
    xAxis: {
      type: "value",
      scale: true, // ROE 可负：禁止从 0 起，负盈利行业必须可见
      name: data.value?.x_label || "ROE(%)",
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { fontSize: 11, color: axisNameColor },
      axisLabel: { fontSize: 11, color: axisLabelColor },
      splitLine: { lineStyle: { color: splitLineColor } }
    },
    yAxis: {
      type: "value",
      scale: true,
      name: data.value?.y_label || "PB",
      nameTextStyle: { fontSize: 11, color: axisNameColor },
      axisLabel: { fontSize: 11, color: axisLabelColor },
      splitLine: { lineStyle: { color: splitLineColor } }
    },
    series: [
      {
        type: "scatter",
        data: points.value,
        symbolSize: 14,
        itemStyle: { color: pointColor, opacity: 0.85 },
        emphasis: {
          itemStyle: { opacity: 1 },
          label: { show: true, fontWeight: 600 }
        },
        // 点旁标注行业名：字号压到 10，避免 ~30 个行业名互相叠压；
        // 叠压时 hover 仍有 tooltip 兜底（emphasis 标签加重）。
        label: {
          show: true,
          position: "right",
          distance: 6,
          fontSize: 10,
          color: axisNameColor,
          formatter: (p: { data?: IndustryPbroePoint }) =>
            p.data?.industry ?? ""
        },
        // ROE=0 参考线：正负盈利区的视觉分界（虚线，弱化不抢点）
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { type: "dashed", color: axisLabelColor, width: 1 },
          label: {
            show: true,
            position: "end",
            fontSize: 10,
            color: axisLabelColor,
            formatter: "ROE=0"
          },
          data: [{ xAxis: 0 }]
        }
      }
    ]
  };
});

async function fetchData() {
  loading.value = true;
  try {
    const res = await getIndustryPbroe();
    // http 封装已解包 axios：res 即后端返回体 { data, message }
    if (res.data) {
      data.value = res.data;
      notice.value = "";
    } else {
      data.value = null;
      notice.value = "行业 PB-ROE 暂不可用，稍后自动恢复";
    }
  } catch (e) {
    console.error("获取行业 PB-ROE 失败:", e);
    data.value = null;
    notice.value = "行业 PB-ROE 暂时取不到，请稍后重试";
  } finally {
    loading.value = false;
  }
}

onMounted(fetchData);
</script>

<style lang="scss" scoped>
/* 卡片外观由 CardBlock 统一提供；外边距与 IndustryCrowdingTrend 对齐（区块纵向节奏） */
.pbroe-scatter {
  margin-bottom: 24px;

  &__updated {
    font-size: var(--text-label);
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  &__chart {
    height: 340px;
  }

  &__canvas {
    width: 100%;
    height: 100%;
  }

  /* 不可用提示（与拥挤度趋势同一视觉语言：提示而非报错） */
  &__empty {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    justify-content: center;
    padding: var(--space-6) var(--space-4);
    font-size: var(--text-label);
    color: var(--text-tertiary);
  }

  &__empty-icon {
    font-size: var(--text-body);
    color: var(--text-tertiary-ink);
  }
}
</style>
