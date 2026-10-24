<template>
  <el-row :gutter="16">
    <el-col :xs="24" :md="12" class="mb-4 md:mb-0">
      <div class="summary-card rounded-2xl p-6 h-full">
        <!-- 左卡竖向节奏：原先是 `flex flex-col justify-between h-full`。
             右卡（280px 图表 + 标题行）比左卡内容高出一大截，`justify-between`
             把这段高度差**全部**变成 hero 与底部三指标之间的空洞，三指标被顶到
             卡片最底边、看起来像掉队的一行。改为**整组垂直居中 + 固定紧凑间距**：
             剩余高度均分到上下两侧，卡片读起来是「有意留白」而不是「内容被撑散」。
             `h-full` 保留（与右卡等高是两卡并排的基本秩序），但它不再参与内部排布。 -->
        <div class="summary-card__stack">
          <div class="summary-card__hero">
            <p class="summary-card__label">总资产（本月）</p>
            <!-- 总资产是**存量**不是盈亏：design.md「指标数值不染涨跌色」。
                 `MoneyDisplay` 的 `auto-color` 默认开着，值 > 0 时会把 48px 的
                 主数字染成涨红——主数字被染红既与语义不符，也让下面三列的中性
                 基调被拉偏。故显式关掉 autoColor 并给 --text-primary。 -->
            <MoneyDisplay
              :value="totalAssets"
              size="hero"
              :show-sign="false"
              :show-currency="true"
              :auto-color="false"
              custom-color="var(--text-primary)"
            />
            <!-- 环比 / 同比：标签在前、数值在后（原先是「数值 较上月」）。
                 「+1.24% 较上月」要回读一遍才知道是什么，「较上月 +1.24%」不用。 -->
            <div class="summary-card__deltas">
              <div class="summary-card__delta">
                <span class="summary-card__delta-label">较上月</span>
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
                  <span class="summary-card__delta-none">——</span>
                </el-tooltip>
              </div>
              <div class="summary-card__delta">
                <span class="summary-card__delta-label">较去年同期</span>
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
                  <span class="summary-card__delta-none">——</span>
                </el-tooltip>
              </div>
            </div>
          </div>

          <div class="summary-card__rule" />

          <!-- 三列之间用竖细线分隔而不是各给一个底色块：它们是同一组指标的
               三个并列视角，给底色块会读成三张独立小卡、反而割裂。 -->
          <div class="summary-card__metrics">
            <div class="summary-card__metric">
              <p class="summary-card__metric-label">总负债</p>
              <MoneyDisplay
                :value="totalLiabilities"
                size="md"
                :show-sign="false"
                :show-currency="true"
                :auto-color="false"
                custom-color="var(--text-primary)"
              />
            </div>
            <div class="summary-card__metric">
              <p class="summary-card__metric-label">净资产</p>
              <MoneyDisplay
                :value="totalAssets - totalLiabilities"
                size="md"
                :show-sign="false"
                :show-currency="true"
                :auto-color="false"
                custom-color="var(--text-primary)"
              />
            </div>
            <div class="summary-card__metric">
              <p class="summary-card__metric-label">总盈亏</p>
              <!-- 唯一保留涨红跌绿的一格：它本来就是盈亏口径 -->
              <MoneyDisplay :value="totalPnl" size="md" :show-currency="true" />
            </div>
          </div>
        </div>
      </div>
    </el-col>

    <el-col :xs="24" :md="12">
      <div class="summary-card rounded-2xl p-6 h-full">
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
import { ref, watch, onMounted, nextTick } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import {
  type AssetSnapshotItem,
  type DistributionsData,
  type PnlCalendarGranularity
} from "@/api/summary";
import PnlCalendar from "@/components/PnlCalendar/index.vue";
import PnlCalendarCaliberIcon from "@/components/PnlCalendar/PnlCalendarCaliberIcon.vue";
import echarts from "@/plugins/echarts";
import { getCssVar } from "@/composables/echarts/theme";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import {
  buildWaterfallBars,
  buildWaterfallOption,
  hasWaterfallData
} from "./assetWaterfall";

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
  distributions: DistributionsData | null;
}>();

const waterfallChartRef = ref<HTMLElement | null>(null);
/**
 * #1925：右列卡片体的原地开关——false = 资产大类瀑布图，true = 收益日历。
 * （#1812 的 `calendarVisible` 弹窗形态已随本卡移除。）
 */
const calendarMode = ref(false);

// #2164：实例生命周期（init / window resize / 卸载 dispose / 主题重绘 /
// keepAlive 恢复时 resize）移交 `useEchartsLifecycle`。默认的全量重建语义正好
// 匹配本组件原行为（每次都 dispose + 重新 init），故不必开 `reuse`。
const { render, charts } = useEchartsLifecycle(
  [
    {
      ref: waterfallChartRef,
      build: el => {
        const chart = echarts.init(el);
        if (!drawableWaterfall()) {
          chart.dispose();
          return chart;
        }
        const bars = buildWaterfallBars(props.distributions!);
        chart.setOption(
          buildWaterfallOption(bars, {
            rise: getCSSColor("--color-rise"),
            fall: getCSSColor("--color-fall"),
            info: getCSSColor("--color-info"),
            neutral: getCSSColor("--color-neutral"),
            // 轴标签也是文字：design.md 规定 `color:` 用途一律走 --text-tertiary-ink
            //（--text-tertiary 白底仅 3.69:1，达不到正文 4.5:1）
            axis: getCSSColor("--text-tertiary-ink"),
            border: getCSSColor("--border-light"),
            // 连接线取 --text-tertiary：colors.css 把它定义为「辅助底色/描边/图形」级，
            // 正好是瀑布台阶的语义。--border-default 在白卡上只有 ~11% 明度差，
            // 1px 虚线实际看不见（实测），等于白画。
            connector: getCSSColor("--text-tertiary"),
            // 柱标签文字色：**必须传解析后的颜色**（这里是 getCssVar 读出来的实际值），
            // 传给 echarts canvas 的 `var(--x)` 会被静默忽略 ⇒ 标签颜色不可控
            riseInk: getCSSColor("--color-rise-ink"),
            fallInk: getCSSColor("--color-fall-ink"),
            neutralInk: getCSSColor("--text-secondary"),
            primaryInk: getCSSColor("--text-primary")
          })
        );
        return chart;
      }
    }
  ],
  // 首次绘制由 onMounted / distributions watcher 触发（都已在原文件里）
  { keepAlive: true, autoRenderOnMount: false }
);

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
    // 容器已被摘下，手动交回收（composable 不提供「临时释放单个实例」的 API，
    // 这里直接操作它暴露的 charts 数组——下次 render 会因数组已清空而重新 build）
    charts.forEach(c => c?.dispose());
    charts.length = 0;
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
  if (!props.distributions) return;
  // 消费后端 distributions：资产大类瀑布（真实数据，非模拟）。
  // 无可画的数据时直接返回，保留空白绘图区而不是画一张全 0 的空图。
  if (!hasWaterfallData(props.distributions)) return;

  render();
}

/*
 * 柱几何与 option 构造已抽到 `assetWaterfall.ts`（纯计算，不碰 DOM / 实例）。
 * 本文件只保留「什么时候画、画在哪个 DOM 上」——那部分与 `toggleCalendar` 的两态
 * 时序耦合，不能搬走；「什么时候 dispose」已移交 useEchartsLifecycle。
 */

// 瀑布图在日历态下没有任何可画数据（容器已被 v-else 摘掉），build 里直接交回收，
// 避免画出一张全 0 的空图。返回的实例已是 disposed，composable 下次 render 会重建。
function drawableWaterfall(): boolean {
  return (
    !calendarMode.value &&
    !!waterfallChartRef.value &&
    !!props.distributions &&
    hasWaterfallData(props.distributions)
  );
}

// distributions 异步到达 / 刷新时重绘瀑布图（容器常驻，无需等待挂载）
watch(
  () => props.distributions,
  async () => {
    await nextTick();
    initWaterfallChart();
  }
);

// 主题切换（暗色）由 composable 内置的 `watch(themeTick, render)` 覆盖（#2164），
// 不再在本文件重复写一遍。

onMounted(() => {
  if (props.distributions) initWaterfallChart();
});
</script>

<style scoped>
/* 两张卡的底色 / 描边 / 阴影 / hover 收敛到同一条规则：
   原本它们各自写了一份**内联 style**（backgroundColor / border / boxShadow），
   而 hover 的 `--shadow-float` 写在 `.summary-card:hover` 这个 class 规则里——
   内联样式的优先级高于任何 class 规则，于是 hover 一直是段死代码。
   现在全部下沉到本规则，两卡 hover 行为也终于一致。 */
.summary-card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-raised);
  transition: box-shadow 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.summary-card:hover {
  box-shadow: var(--shadow-float);
}

/* 卡片体锁高 280px（#2033）：瀑布图态与日历态共用同一个高度，切换零跳变，
   两卡底边恒对齐。**是 height，不是 min-height**——min-height 在内容更高时
   会把卡片顶高，两态高度不同的问题原封不动地回来了。数字沿用瀑布图原有的
   280，不新增常量；内部两个内容容器都用 h-full 填满它，高度约束只由宿主
   （本卡）施加。 */
.overview-card__body {
  height: 280px;
}

/* #2039 兜底，**仅本卡**：收益日历那排控件（3 枚 SegmentedControl + 区间导航）
   实测宽 588px，本卡半宽容器装不下时若既不能收缩也不能换行，就会横向溢出。
   ⚠️ **只打本卡，不要改全站 SectionHeader**——那两个宿主（投资概览第三排、
   账户详情）是满宽 / 半宽的正常容器，兜底不需要蔓延过去。
   本卡是 host-header 模式，PnlCalendar 不画 SectionHeader，控件排实际落在
   `.pnl-calendar__controls` 上，故两个选择器都兜一份。
   选择器锚点用 `.summary-card`（本卡两卡共用），左卡内无这些子元素，不受影响。 */
.summary-card :deep(.section-header__action),
.summary-card :deep(.pnl-calendar__controls) {
  flex-shrink: 1;
  flex-wrap: wrap;
  min-width: 0;
}

.summary-card__stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
  justify-content: center;
  height: 100%;
}

.summary-card__label {
  margin: 0 0 6px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 环比 / 同比成对出现：行内两列，列间距 20px（4px 基数）。
   与上方大数字拉开 16px —— 这三行是「一个数 + 它的两个参照」，
   12px 会让参照读起来像数字的注解，20px 又只剩空。 */
.summary-card__deltas {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin-top: 16px;
}

.summary-card__delta {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
}

.summary-card__delta-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.summary-card__delta-none {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 卡片内部两级分割线：
   · 摘要区 → 三指标这一道是**结构性断点**，与卡片外框同重量（--border-light）；
   · 三列之间的竖线是**同级并列**的弱分隔，降到 --border-subtle（design.md：
     卡片内部降权分割线用它）。
   两级都走令牌，且竖线明显轻于横线——顺序反过来会让三列看起来像一张表格。 */
.summary-card__rule {
  height: 1px;
  background-color: var(--border-light);
}

.summary-card__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.summary-card__metric {
  min-width: 0;
  /* 竖线与两侧内容各留 16px：线是分隔，不是内容边界，贴上去会读成「线压着字」 */
  padding: 0 var(--space-compact);
}

.summary-card__metric:first-child {
  padding-left: 0;
}

.summary-card__metric:last-child {
  padding-right: 0;
}

.summary-card__metric + .summary-card__metric {
  border-left: 1px solid var(--border-subtle);
}

/* 标签与数字的层级：13px 辅助色标签 + 16px 主文字数字，标签不抢数字。
   6px 间距让「标签→数字」成为一组，而不是两行无关文字。 */
.summary-card__metric-label {
  margin: 0 0 6px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 开关态（#1925）：切到收益日历时点亮图标，与标题变化一起回答「现在看的是哪个」。
   颜色走语义令牌，禁硬编码 hex（design.md 硬约束）；特异性
   `.summary-card__toggle.is-on[data-v-*]` 高于 EP 的 `.el-button.is-text`，无需 !important。 */
.summary-card__toggle.is-on {
  color: var(--brand-700);
}
</style>
