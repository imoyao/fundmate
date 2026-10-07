<template>
  <el-row :gutter="16">
    <el-col :xs="24" :md="12" class="mb-4 md:mb-0">
      <div
        class="summary-card rounded-2xl p-6 h-full"
        :style="{
          backgroundColor: 'var(--bg-card)',
          boxShadow: 'var(--shadow-raised)',
          border: '1px solid var(--border-light)'
        }"
      >
        <div class="flex flex-col justify-between h-full">
          <div>
            <p
              class="text-sm mb-2"
              :style="{ color: 'var(--text-tertiary-ink)' }"
            >
              总资产（本月）
            </p>
            <MoneyDisplay
              :value="totalAssets"
              size="hero"
              :show-sign="false"
              :show-currency="true"
            />
            <div class="flex items-center gap-4 mt-3">
              <template v-if="latestSnapshot?.monthly_change_pct != null">
                <RiseFallText
                  :value="latestSnapshot.monthly_change_pct"
                  suffix="%"
                  size="sm"
                />
              </template>
              <el-tooltip
                v-else
                content="暂无上月同期数据，持续使用后自动积累"
                placement="top"
              >
                <span
                  class="text-sm"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                  >——</span
                >
              </el-tooltip>
              <span
                class="text-xs"
                :style="{ color: 'var(--text-tertiary-ink)' }"
                >较上月</span
              >
              <template v-if="latestSnapshot?.yearly_change_pct != null">
                <RiseFallText
                  :value="latestSnapshot.yearly_change_pct"
                  suffix="%"
                  size="sm"
                />
              </template>
              <el-tooltip
                v-else
                content="暂无去年同期数据，持续使用后自动积累"
                placement="top"
              >
                <span
                  class="text-sm"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                  >——</span
                >
              </el-tooltip>
              <span
                class="text-xs"
                :style="{ color: 'var(--text-tertiary-ink)' }"
                >较去年同期</span
              >
            </div>
          </div>
          <div
            class="my-5"
            :style="{ borderTop: '1px solid var(--border-light)' }"
          />
          <div class="grid grid-cols-3 gap-4">
            <div>
              <p
                class="text-xs mb-1"
                :style="{ color: 'var(--text-tertiary-ink)' }"
              >
                总负债
              </p>
              <MoneyDisplay
                :value="totalLiabilities"
                size="md"
                :show-sign="false"
                :show-currency="true"
              />
            </div>
            <div>
              <p
                class="text-xs mb-1"
                :style="{ color: 'var(--text-tertiary-ink)' }"
              >
                净资产
              </p>
              <MoneyDisplay
                :value="totalAssets - totalLiabilities"
                size="md"
                :show-sign="false"
                :show-currency="true"
              />
            </div>
            <div>
              <p
                class="text-xs mb-1"
                :style="{ color: 'var(--text-tertiary-ink)' }"
              >
                总盈亏
              </p>
              <MoneyDisplay :value="totalPnl" size="md" :show-currency="true" />
            </div>
          </div>
        </div>
      </div>
    </el-col>

    <el-col :xs="24" :md="12">
      <div
        class="rounded-2xl p-6 h-full"
        :style="{
          backgroundColor: 'var(--bg-card)',
          boxShadow: 'var(--shadow-raised)',
          border: '1px solid var(--border-light)'
        }"
      >
        <div class="flex justify-between items-center mb-4">
          <h3 class="font-semibold" :style="{ color: 'var(--text-primary)' }">
            {{ calendarMode ? "收益日历" : "总资产构成" }}
          </h3>
          <!-- #1812：这个日历图标自设计起就是「资产月历」的预留入口
               （tooltip 曾写「后续版本推出」）。#1925 把它从「唤起弹窗」改成
               **原地开关**：右列卡片体在瀑布图与收益日历之间切换，左列摘要卡
               不动，页面不再被遮罩盖住。
               标题 / tooltip / aria-label / 图标四者必须同步变——只换标题会让
               用户找不到回去的路（这正是「关闭要先于关闭之前问」的老问题的镜像）。 -->
          <el-tooltip
            :content="calendarMode ? '返回总资产构成' : '收益日历'"
            placement="top"
          >
            <el-button
              text
              size="small"
              class="summary-card__toggle"
              :class="{ 'is-on': calendarMode }"
              :aria-label="calendarMode ? '返回总资产构成' : '打开收益日历'"
              @click="toggleCalendar"
            >
              <IconifyIconOffline
                :icon="calendarMode ? 'ep:data-line' : 'ep:calendar'"
                class="text-base"
              />
            </el-button>
          </el-tooltip>
        </div>

        <!-- L2 容器：收益日历原地切换态。与 welcome 第三排 / 账户详情是
             **同一组件的三处容器**，口径唯一。 -->
        <div v-if="calendarMode" class="min-h-[280px]">
          <PnlCalendar />
        </div>
        <div v-else ref="waterfallChartRef" class="h-[280px]" />
      </div>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import { type AssetSnapshotItem } from "@/api/summary";
import PnlCalendar from "@/components/PnlCalendar/index.vue";
import echarts from "@/plugins/echarts";
import { getCssVar, useThemeTick } from "@/composables/echarts/theme";

const props = defineProps<{
  totalAssets: number;
  totalLiabilities: number;
  totalPnl: number;
  latestSnapshot: AssetSnapshotItem | null;
  distributions: any;
}>();

const waterfallChartRef = ref<HTMLDivElement>();
let waterfallChart: echarts.ECharts | null = null;
const themeTick = useThemeTick();
/**
 * #1925：右列卡片体的原地开关——false = 总资产构成瀑布图，true = 收益日历。
 * （#1812 的 `calendarVisible` 弹窗形态已随本卡移除。）
 */
const calendarMode = ref(false);

/**
 * 切换右列卡片体。
 *
 * 关键在**离开日历态**那一步：图表容器被 `v-else` 摘下后，旧实例仍握着已脱离
 * 文档的 DOM，不释放会一直占着内存；而**回到图表态**必须等 DOM 挂回来才能
 * `echarts.init`——这正是 `nextTick()` 存在的理由，少了它第一次切回必白屏。
 */
async function toggleCalendar() {
  calendarMode.value = !calendarMode.value;
  await nextTick();
  if (calendarMode.value) {
    waterfallChart?.dispose();
    waterfallChart = null;
    return;
  }
  initWaterfallChart();
}

// 工具函数：安全读取 CSS 变量（无 fallback 硬编码）
const getCSSColor = (varName: string): string => {
  return getCssVar(varName);
};

function initWaterfallChart() {
  // 日历态下容器不存在（v-else 已摘掉），交给 toggleCalendar 统一处理；
  // distributions / 主题的 watcher 可能在日历态下触发，这里必须短路
  if (calendarMode.value) return;
  if (!waterfallChartRef.value) return;
  if (waterfallChart) waterfallChart.dispose();
  waterfallChart = echarts.init(waterfallChartRef.value);

  // 消费后端 distributions：总资产构成瀑布（真实数据，非模拟）
  const categories = props.distributions?.category_distribution ?? [];
  const totalLiab = props.distributions?.total_liabilities ?? 0;
  const netWorth = props.distributions?.net_worth ?? 0;
  if (categories.length === 0 && totalLiab <= 0) return;

  const primaryColor = getCSSColor("--brand-700");
  const infoColor = getCSSColor("--color-info");
  const riseColor = getCSSColor("--color-rise");
  const fallColor = getCSSColor("--color-fall");
  const neutralColor = getCSSColor("--color-neutral");

  const start = 0;
  const changes = [
    ...categories.map(c => ({ name: c.name, value: c.value })),
    ...(totalLiab > 0 ? [{ name: "负债", value: -totalLiab }] : [])
  ];
  const end = netWorth;
  const cumulativeValues: number[] = [start];
  changes.forEach((item, index) => {
    cumulativeValues.push(cumulativeValues[index] + item.value);
  });
  const allData = [
    { name: "起点", height: start, change: start, isEndpoint: true },
    ...changes.map((item, index) => ({
      name: item.name,
      height: cumulativeValues[index + 1],
      change: item.value,
      isEndpoint: false
    })),
    { name: "净资产", height: end, change: end, isEndpoint: true }
  ];

  waterfallChart.setOption({
    tooltip: { trigger: "axis" },
    grid: { left: "8%", right: "4%", top: 20, bottom: 50, containLabel: true },
    xAxis: {
      type: "category",
      data: allData.map(d => d.name),
      axisLabel: {
        rotate: 30,
        fontSize: 10,
        color: getCSSColor("--text-tertiary")
      },
      axisLine: { lineStyle: { color: getCSSColor("--border-light") } }
    },
    yAxis: {
      type: "value",
      min: 0,
      splitLine: { lineStyle: { color: getCSSColor("--border-light") } },
      axisLabel: {
        color: getCSSColor("--text-tertiary"),
        fontSize: 11,
        formatter: (v: number) => v.toLocaleString()
      }
    },
    series: [
      {
        type: "bar",
        data: allData.map(d => d.height),
        barWidth: "30%",
        barMinHeight: 4,
        itemStyle: {
          borderRadius: 4,
          color: (params: any) => {
            const d = allData[params.dataIndex];
            if (d.isEndpoint && d.name === "起点") return primaryColor;
            if (d.isEndpoint && d.name === "净资产") return infoColor;
            if (d.change > 0) return riseColor;
            if (d.change < 0) return fallColor;
            return neutralColor;
          }
        },
        label: {
          show: true,
          position: "top",
          fontSize: 10,
          color: getCSSColor("--text-secondary"),
          formatter: (params: any) => {
            const d = allData[params.dataIndex];
            if (d.isEndpoint) return "¥" + d.height.toLocaleString();
            if (d.change === 0) return "¥0";
            return (d.change >= 0 ? "+" : "") + d.change.toLocaleString();
          }
        }
      }
    ]
  });
}

// distributions 异步到达 / 刷新时重绘瀑布图（容器常驻，无需等待挂载）
watch(
  () => props.distributions,
  async () => {
    await nextTick();
    initWaterfallChart();
  }
);

// 主题切换（暗色）时重绘瀑布图，重新读取语义色（#976）
watch(themeTick, () => nextTick(initWaterfallChart));

onMounted(() => {
  if (props.distributions) initWaterfallChart();
});

onBeforeUnmount(() => {
  waterfallChart?.dispose();
  waterfallChart = null;
});
</script>

<style scoped>
.summary-card {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.summary-card:hover {
  box-shadow: var(--shadow-float);
}

/* 开关态（#1925）：切到收益日历时点亮图标，与标题变化一起回答「现在看的是哪个」。
   颜色走语义令牌，禁硬编码 hex（design.md 硬约束）；特异性
   `.summary-card__toggle.is-on[data-v-*]` 高于 EP 的 `.el-button.is-text`，无需 !important。 */
.summary-card__toggle.is-on {
  color: var(--brand-700);
}
</style>
