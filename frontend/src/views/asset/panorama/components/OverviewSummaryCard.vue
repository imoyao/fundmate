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
        <!-- 左卡内部：常规纵向流 + 纵向居中（#2033）。
             原先是 `flex flex-col justify-between h-full` + 中间一条 `my-5` 分割线：
             行高被右卡钉死后，上下两块被推到两头，中间空出一大段，那条分割线
             就**悬在卡片正中**——看着像布局坏了（且「分割线」本身已无信息量：
             上下是同一张卡的两个数字块，不是两个分区）。故删掉分割线、改为 gap-4
             的常规流，内容连成一体。
             `justify-center`（用户拍板）：内容在**锁定高度内**垂直居中，留白上下
             对称（各约 74px），读作有意留白而不是「内容没撑满」。
             ⚠️ 原裁决否掉居中的理由是「切换跳变未消除、居中会跟着一起跳」——
             那个理由**只在行高会变时成立**；行高已由右卡锁死（固定 280px 的卡片体），
             切换零跳变，居中也就随之稳定，故该理由失效。
             `h-full` 是居中的前提：容器高度不确定时 `justify-center` 无效（内容高
             等于容器高，没有可分配的空余）；它同时也是两卡底边恒对齐的依托。 -->
        <div class="flex flex-col justify-center gap-4 h-full">
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
          <!-- 三列 Grid（总负债 / 净资产 / 总盈亏）：作为自然流的一块紧跟涨跌行，
               不再被 justify-between 钉到卡片底边（#2033）。 -->
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
      <!-- 右卡：与左卡并排，**卡片体高度由本卡钉死**（#2033）。
           瀑布图态与日历态的自然高本是两回事（旧口径下 314~604px 随粒度横跳），
           锁成同一个高度后：① 两卡底边恒对齐；② 切换零跳变。
           高度约束**只由宿主施加**，本卡内的两个内容组件各自填满即可
           （PnlCalendar 的「给固定高度就填满、没给就自然高」即为此而来）。 -->
      <div
        class="overview-card rounded-2xl p-6 h-full flex flex-col"
        :style="{
          backgroundColor: 'var(--bg-card)',
          boxShadow: 'var(--shadow-raised)',
          border: '1px solid var(--border-light)'
        }"
      >
        <div class="flex justify-between items-center mb-4">
          <!-- ⓘ 有两枚，按卡片体两态各给一枚，且**都与本行标题同行**：
               · 瀑布图态（#2034）：口径 = 各大类累加后扣负债落到净资产；
               · 日历态（#2050）：口径 = 收益日历自己的口径与图例说明，
                 由 `PnlCalendarCaliberIcon` 提供（视觉契约与 SectionHeader 的
                 `.section-header__info` 完全一致，满宽容器里的 ⓘ 也是它）。

               #2034 收尾（二轮）注：标题原先写成「资产大类构成」，那正好撞上
               `AssetInsightPanel` 切换按钮的字面——按钮态（「资产构成」）与标题态
               （「资产大类构成」）几乎同名，切过去像按住没反应。改成「资产大类」：
               与 (i) 口径说明分工互补（标题给维度，tooltip 给口径），
               也不再与按钮上的字同长。 -->
          <div class="flex items-center gap-1.5">
            <h3 class="font-semibold" :style="{ color: 'var(--text-primary)' }">
              {{ calendarMode ? "收益日历" : "资产大类" }}
            </h3>
            <el-tooltip
              v-if="!calendarMode"
              content="口径：各大类金额逐项累加，扣除负债后落到净资产"
              placement="top"
            >
              <IconifyIconOffline
                icon="ep:info-filled"
                class="text-sm cursor-help"
                :style="{ color: 'var(--text-tertiary-ink)' }"
              />
            </el-tooltip>
            <PnlCalendarCaliberIcon v-else />
          </div>
          <!-- #1812：这个日历图标自设计起就是「资产月历」的预留入口
               （tooltip 曾写「后续版本推出」）。#1925 把它从「唤起弹窗」改成
               **原地开关**：右列卡片体在瀑布图与收益日历之间切换，左列摘要卡
               不动，页面不再被遮罩盖住。
               标题 / tooltip / aria-label / 图标四者必须同步变——只换标题会让
               用户找不到回去的路（这正是「关闭要先于关闭之前问」的老问题的镜像）。
               当心：这四处**不能**写成本卡片对外显示的名字（`AssetInsightPanel`
               的切换按钮就写着它），否则按钮与标题同名，切过去像没切。 -->
          <el-tooltip
            :content="calendarMode ? '返回资产大类' : '收益日历'"
            placement="top"
          >
            <el-button
              text
              size="small"
              class="summary-card__toggle"
              :class="{ 'is-on': calendarMode }"
              :aria-label="calendarMode ? '返回资产大类' : '打开收益日历'"
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
             **同一组件的三处容器**，口径唯一。
             `host-header`（#2050）：上面这个 `<h3>` 已经把「收益日历」写在这里了
             （它必须自己写——另一态是「资产大类」），再让 PnlCalendar 画一遍
             就是两个同名标题上下叠着。`host-header` 让 PnlCalendar 完全不画
             SectionHeader，只输出控件排；口径 ⓘ 由本卡的 `PnlCalendarCaliberIcon`
             与标题同行画出。

             **勿退回 `hide-title`（#2050 回归的根因）**：该 prop 在 #2050 里已被
             删除，写 `hide-title` 只会落成 DOM 上的 `hidetitle=""`，组件走默认
             分支把完整 SectionHeader（标题 + ⓘ + 控件排）重新画一遍 —— 症状是
             截图里那个被控件行挤断成「收益…」的残影 + 独占一行的孤立 ⓘ，
             即 #2035 与 #2050 同时复发。`frontend/e2e/pnl-calendar-host-header.spec.ts`
             断言 `.pnl-calendar .section-header` 计数为 0，但 e2e 不进 per-PR
             门禁，必须靠这里的注释守住。

             **粒度只给月 / 年（#2033）**：日粒度的家在**投资概览页**（welcome 第三排
             的满宽日历），本卡是与左卡并排、卡片体锁死 280px 的**等高兄弟容器**，
             日粒度的「一屏一个月」在这里既排不下也读不清。
             ⚠️ 因此本卡**不提供日粒度，也不提供任何入口**（没有「展开 / 查看大图」，
             已裁决）——日粒度的需求去 welcome 即可。请勿「好心」把日粒度加回来：
             下钻链（年→月→日）的最后一级正是日粒度，只在控件排里挡而不在
             PnlCalendar 的下钻里挡，用户就会掉进一个本卡装不下、且没有控件能切回来的形态。 -->
        <div class="overview-card__body">
          <div v-if="calendarMode" class="h-full">
            <PnlCalendar host-header :granularities="PANORAMA_GRANULARITIES" />
          </div>
          <div v-else ref="waterfallChartRef" class="h-full" />
        </div>
      </div>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import {
  type AssetSnapshotItem,
  type PnlCalendarGranularity
} from "@/api/summary";
import PnlCalendar from "@/components/PnlCalendar/index.vue";
import PnlCalendarCaliberIcon from "@/components/PnlCalendar/PnlCalendarCaliberIcon.vue";
import echarts from "@/plugins/echarts";
import { getCssVar, useThemeTick } from "@/composables/echarts/theme";

/**
 * 本卡允许的收益日历粒度（#2033）：**只有月 / 年，没有日**。
 *
 * 日粒度的家在投资概览页（welcome 第三排的满宽日历）；本卡是与摘要卡并排、
 * 卡片体锁死 280px 的等高兄弟容器，日粒度的「一屏一个月」在这里排不下也读不清。
 * 本卡**不提供日粒度、也不提供任何入口**（没有「展开 / 查看大图」，已裁决）——
 * 请勿「好心」把它加回来。
 */
const PANORAMA_GRANULARITIES: readonly PnlCalendarGranularity[] = [
  "month",
  "year"
];

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
 * #1925：右列卡片体的原地开关——false = 资产大类瀑布图，true = 收益日历。
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

  // 消费后端 distributions：资产大类瀑布（真实数据，非模拟）
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

/* 卡片体锁高 280px（#2033）：瀑布图态与日历态共用同一个高度，切换零跳变。
   **是 height，不是 min-height**——min-height 在内容更高时会把卡片顶高，
   两态高度不同的问题原封不动地回来了。数字沿用瀑布图原有的 280，不新增常量。
   两个内容容器都用 h-full 填满它，高度约束只由宿主（本卡）施加。 */
.overview-card__body {
  height: 280px;
}

/* #2039 兜底，**仅本容器**：收益日历那排控件（3 枚 SegmentedControl + 区间导航）
   实测宽 588px，本卡半宽容器装不下时若既不能收缩也不能换行，就会横向溢出、
   叠到左侧的 ⓘ 上。全站 `SectionHeader` 的操作槽已经能收缩（见其样式注释），
   这里对同一类操作槽再兜一层。
   ⚠️ **只打本容器，不要改全站 SectionHeader**——那两个宿主（投资概览第三排、
     账户详情）是满宽 / 半宽的正常容器，兜底不需要蔓延过去。
   本卡是 host-header 模式，PnlCalendar 不画 SectionHeader，控件排实际落在
   `.pnl-calendar__controls` 上，故两个选择器都兜一份。 */
.overview-card :deep(.section-header__action),
.overview-card :deep(.pnl-calendar__controls) {
  flex-shrink: 1;
  flex-wrap: wrap;
  min-width: 0;
}

/* 开关态（#1925）：切到收益日历时点亮图标，与标题变化一起回答「现在看的是哪个」。
   颜色走语义令牌，禁硬编码 hex（design.md 硬约束）；特异性
   `.summary-card__toggle.is-on[data-v-*]` 高于 EP 的 `.el-button.is-text`，无需 !important。 */
.summary-card__toggle.is-on {
  color: var(--brand-700);
}
</style>
