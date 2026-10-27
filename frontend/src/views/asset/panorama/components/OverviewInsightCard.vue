<!--
  OverviewInsightCard · 资产全景右卡（#980 批 B6 从 `OverviewSummaryCard.vue` 抽出）

  卡片体两态原地切换（#1925）：构成图 ⇄ 收益日历。左列摘要卡不动，页面不再被
  遮罩盖住（#1812 的弹窗形态已移除）。

  ⚠️ 这个文件里最容易被改坏的是三处约定，都写在下面对应位置的注释里：
  1. `host-header` 而不是 `hide-title`（#2050）；
  2. 粒度只给月 / 年，且不提供任何日粒度入口（#2033）；
  3. 切态时图表的 dispose / 重建必须落在 `nextTick` 之后，否则第一次切回白屏。
-->
<template>
  <div class="summary-card rounded-2xl p-6 h-full">
    <div class="flex justify-between items-center mb-4">
      <!-- ⓘ 有两枚，按卡片体两态各给一枚，且**都与本行标题同行**：
           · 构成图态：口径 = 只统计资产端各类金额，负债与净资产见左卡；
           · 日历态（#2050）：口径 = 收益日历自己的口径与图例说明，由
             `PnlCalendarCaliberIcon` 提供（契约同 SectionHeader 的 ⓘ）。

           口径文案只守一条：**图说什么，ⓘ 就说什么**。#2034 那句「逐项累加，
           扣除负债后落到净资产」是瀑布图的口径，改成构成图后负债已不在图内，
           必须同步改。标题也不再叫「资产大类构成」——与切换按钮「资产构成」
           几乎同名，切过去像按住没反应（#2034 二轮）。 -->
      <div class="flex items-center gap-1.5">
        <h3 class="font-semibold" :style="{ color: 'var(--text-primary)' }">
          {{ calendarMode ? "收益日历" : "资产大类" }}
        </h3>
        <el-tooltip
          v-if="!calendarMode"
          content="口径：只统计资产端各大类金额，负债与净资产见左侧卡片"
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
           **原地开关**：右列卡片体在构成图与收益日历之间切换，左列摘要卡
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
      <div v-else ref="compositionChartRef" class="h-full" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  type DistributionsData,
  type PnlCalendarGranularity
} from "@/api/summary";
import PnlCalendar from "@/components/PnlCalendar/index.vue";
import PnlCalendarCaliberIcon from "@/components/PnlCalendar/PnlCalendarCaliberIcon.vue";
import echarts from "@/plugins/echarts";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import { hasCompositionData } from "./assetComposition";
import { buildCompositionViewOption } from "./compositionView";

defineOptions({ name: "OverviewInsightCard" });

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
  /** 后端资产大类构成；null = 尚未取到，绘图区留白不画空图 */
  distributions: DistributionsData | null;
}>();

const compositionChartRef = ref<HTMLElement | null>(null);
/**
 * #1925：卡片体的原地开关——false = 资产大类构成图，true = 收益日历。
 * （#1812 的 `calendarVisible` 弹窗形态已随本卡移除。）
 */
const calendarMode = ref(false);

// #2164：实例生命周期（init / window resize / 卸载 dispose / 主题重绘 /
// keepAlive 恢复时 resize）移交 `useEchartsLifecycle`。默认的全量重建语义正好
// 匹配本组件原行为（每次都 dispose + 重新 init），故不必开 `reuse`。
const { render, charts } = useEchartsLifecycle(
  [
    {
      ref: compositionChartRef,
      build: el => {
        const chart = echarts.init(el);
        if (!drawableComposition()) {
          chart.dispose();
          return chart;
        }
        // 取色与 option 组装在 `compositionView.ts`（本文件在 #980 的页面规模基线内，
        // 只减不增）。**不传高度**：构成图没有按像素判定的几何，容器尺寸交给 resize。
        chart.setOption(buildCompositionViewOption(props.distributions!));
        return chart;
      }
    }
  ],
  // 首次绘制由 onMounted / distributions watcher 触发（都已在原文件里）
  { keepAlive: true, autoRenderOnMount: false }
);

/**
 * 切换卡片体。
 *
 * 关键在**离开日历态**那一步：图表容器被 `v-else` 摘下后，旧实例仍握着已脱离
 * 文档的 DOM，不释放会一直占着内存；而**回到图表态**必须等 DOM 挂回来才能
 * `echarts.init`——这正是 `nextTick()` 存在的理由，少了它第一次切回必白屏。
 */
async function toggleCalendar() {
  calendarMode.value = !calendarMode.value;
  await nextTick();
  if (calendarMode.value) {
    // 容器已被摘下，手动交回收（composable 不提供「临时释放单个实例」的 API，
    // 这里直接操作它暴露的 charts 数组——下次 render 会因数组已清空而重新 build）
    charts.forEach(c => c?.dispose());
    charts.length = 0;
    return;
  }
  initCompositionChart();
}

function initCompositionChart() {
  // 日历态下容器不存在（v-else 已摘掉），交给 toggleCalendar 统一处理；
  // distributions / 主题的 watcher 可能在日历态下触发，这里必须短路
  if (calendarMode.value) return;
  if (!compositionChartRef.value) return;
  if (!props.distributions) return;
  // 消费后端 distributions：资产大类构成（真实数据，非模拟）。
  // 无可画的数据时直接返回，保留空白绘图区而不是画一张全 0 的空图。
  if (!hasCompositionData(props.distributions)) return;

  render();
}

/*
 * 数据整形与 option 构造在 `assetComposition.ts`（纯计算，不碰 DOM / 实例），
 * 取色在 `compositionView.ts`。本文件只保留「什么时候画、画在哪个 DOM 上」——
 * 那部分与 `toggleCalendar` 的两态时序耦合，不能搬走；「什么时候 dispose」
 * 已移交 useEchartsLifecycle。
 */

// 日历态下没有任何可画数据（容器已被 v-else 摘掉），build 里直接交回收，
// 避免画出一张全 0 的空图。返回的实例已是 disposed，composable 下次 render 会重建。
function drawableComposition(): boolean {
  return (
    !calendarMode.value &&
    !!compositionChartRef.value &&
    !!props.distributions &&
    hasCompositionData(props.distributions)
  );
}

// distributions 异步到达 / 刷新时重绘（容器常驻，无需等待挂载）
watch(
  () => props.distributions,
  async () => {
    await nextTick();
    initCompositionChart();
  }
);

// 主题切换（暗色）由 composable 内置的 `watch(themeTick, render)` 覆盖（#2164），
// 不再在本文件重复写一遍。
onMounted(() => {
  if (props.distributions) initCompositionChart();
});
</script>

<style lang="scss" scoped>
@use "./summary-card" as *;

/* 卡片体锁高 280px（#2033）：构成图态与日历态共用同一个高度，切换零跳变，
   两卡底边恒对齐。**是 height，不是 min-height**——min-height 在内容更高时
   会把卡片顶高，两态高度不同的问题原封不动地回来了。数字沿用构成图前身（瀑布图）
   的 280，不新增常量；内部两个内容容器都用 h-full 填满它，高度约束只由宿主
   （本卡）施加。 */
.overview-card__body {
  height: 280px;
}

/* #2039 兜底，**仅本卡**：收益日历那排控件（3 枚 SegmentedControl + 区间导航）
   实测宽 588px，本卡半宽容器装不下时若既不能收缩也不能换行，就会横向溢出。
   ⚠️ **只打本卡，不要改全站 SectionHeader**——那两个宿主（投资概览第三排、
   账户详情）是满宽 / 半宽的正常容器，兜底不需要蔓延过去。
   本卡是 host-header 模式，PnlCalendar 不画 SectionHeader，控件排实际落在
   `.pnl-calendar__controls` 上，故两个选择器都兜一份。 */
.summary-card :deep(.section-header__action),
.summary-card :deep(.pnl-calendar__controls) {
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
