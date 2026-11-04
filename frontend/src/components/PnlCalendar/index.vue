<!--
  PnlCalendar · 收益日历（#1812 日视图 / #1925 三视图 / #1942 方格图与六态）

  一组件多容器：welcome 嵌入卡（满宽 12 列）、panorama「资产大类」原地切换、
  账户详情半宽容器，共用同一份数据与口径。

  三视图（#1925）× 两种形态（#1942）：
    日收益  按月翻；日历图（一屏一个月）/ 柱状图（一根柱 = 一天）
    月收益  按年翻；方格图（12 个月各一格）/ 柱状图（一根柱 = 一个月）
    年收益  **投资以来**全览，一格一年（区间固定，故无区间导航）；两种形态同上
    点击下钻：年格 → 该年的月格 → 该月的日日历
  三者**不是三条口径**，而是同一条日序列的三种切法——聚合下推在后端
  （`granularity` 参数），前端只做呈现，禁止二次盈亏计算。

  六态视觉与色彩纪律集中在 `PnlCalendarTile.vue`（格子）与 `PnlCalendarBars.vue`（柱）：
    updown       涨红跌绿柔和填充，色深 ∝ |收益|
    zero         灰底 + 0.00（真实为零）
    no_price     斜线纹理（balance 模式无历史价格序列，如银行理财/投顾/实物）
    no_data      虚线 + 「未同步」（开盘日却没取到当天估值）
    no_position  虚线 + 「无持仓」（建仓前 / 清仓后）
    closed       空白 + 「休市」（非 A 股开盘日；判据是后端交易日历，不是「有没有价格」）
  **缺数据绝不能画成 0**，这是本组件存在的核心理由之一。
  「休市」与「未同步」必须分开（#1942）：前者只能等开盘，后者要去跑同步任务。

  #980 拆分（纯搬运，零视觉/行为变更）：
    · 状态机（取数区间 / 游标 / 下钻 / 空态归因）→ `usePnlCalendarData.ts`
    · 加载 / 错误 / 空态三块 → `PnlCalendarPlaceholder.vue`
    · 合计行 → `PnlCalendarSummary.vue`
    · 三种「空」的判据与文案 → `emptyState.ts`（纯函数，单测直接覆盖）
  本文件只留模板装配与 props 契约。
-->

<template>
  <div class="pnl-calendar">
    <!-- ===== 标题行 =====
         两种模式（#2050）：

         · `hostHeader=false`（默认）：组件自画完整 SectionHeader——标题 + 口径 ⓘ
           + 控件排。投资概览第三排、账户详情用此模式。

         · `hostHeader=true`：标题与口径 ⓘ **一并交给宿主**，组件只输出控件排
           （右对齐）。资产总览右卡用此模式——宿主必须自己画 `<h3>`（它要在
           「资产大类 / 收益日历」之间变），若组件再画一遍就会出现两个同名标题
           上下叠着（#2035 的旧 `hideTitle` 只抑制了 `<h2>` 文字，ⓘ 仍独占一行，
           形成孤立伪标题行——#2050 修的正是这个）。宿主侧用
           `PnlCalendarCaliberIcon` 在自画标题旁补上 ⓘ。 -->
    <SectionHeader
      v-if="!hostHeader"
      title="收益日历"
      info-label="收益日历的口径与图例说明"
    >
      <template #info>
        <PnlCalendarCaliberTip />
      </template>
      <template #action>
        <PnlCalendarActionBar
          v-model:granularity="cal.granularity"
          v-model:view="cal.view"
          v-model:value-mode="cal.valueMode"
          :loading="cal.loading"
          :range-label="cal.rangeLabel"
          :granularities="cal.allowedGranularities"
          @shift="cal.shift"
          @go-current="cal.goCurrent"
        />
      </template>
    </SectionHeader>
    <div v-else class="pnl-calendar__controls">
      <PnlCalendarActionBar
        v-model:granularity="cal.granularity"
        v-model:view="cal.view"
        v-model:value-mode="cal.valueMode"
        :loading="cal.loading"
        :range-label="cal.rangeLabel"
        :granularities="cal.allowedGranularities"
        @shift="cal.shift"
        @go-current="cal.goCurrent"
      />
    </div>

    <!-- ===== 加载 / 空态 / 错误 ===== -->
    <PnlCalendarPlaceholder v-if="cal.loading" kind="loading" />
    <PnlCalendarPlaceholder
      v-else-if="cal.error"
      kind="error"
      :text="cal.error"
      @retry="cal.load"
    />
    <!-- 无价格序列：明确说清原因，不画成零收益（否则用户以为坏了）。
         数据缺口时额外给出口：用户能一键跳到有数据的那一期，
         否则只能自己一次次翻区间试。 -->
    <PnlCalendarPlaceholder
      v-else-if="!cal.hasAnyPrice"
      kind="empty"
      :text="cal.emptyHint"
      :jump-text="
        cal.emptyIsDataGap && cal.latestPriceLabel ? cal.jumpButtonText : ''
      "
      @jump="cal.jumpToLatestPrice"
    />

    <!-- ===== 主体：方格图（日历图 / 月格 / 年格）/ 柱状图 =====
         外面这一层 `pnl-calendar__body` 只负责一件事：**跟随宿主的高度**
         （#2033）。宿主给了确定高度（资产总览右卡的等高容器）就填满，
         没给（welcome 满宽 / 账户详情半宽）就是自然高——高度约束只能由宿主施加，
         本组件不自带任何固定高度，那两处的排版因此与改动前逐像素一致。 -->
    <template v-else>
      <div class="pnl-calendar__body">
        <PnlCalendarGrid
          v-if="cal.granularity === 'day' && cal.view === 'calendar'"
          :days="cal.series?.days ?? []"
          :year="cal.cursor.getFullYear()"
          :month-index="cal.cursor.getMonth()"
          :mode="cal.valueMode"
        />

        <!-- 月 / 年视图的方格图（#1942）：一格一个期间，点击下钻 -->
        <PnlCalendarPeriodGrid
          v-else-if="cal.granularity !== 'day' && cal.view === 'calendar'"
          :periods="cal.series?.periods ?? []"
          :granularity="cal.granularity"
          :mode="cal.valueMode"
          @select="cal.selectPeriod"
        />

        <!-- 柱状图：三粒度共用一份几何，只是「一根柱」的含义不同（见文件头）。
             后端保证 days / periods 只有一侧非空，Bars 内部据此选边。
             月 / 年视图的柱一根 = 一月 / 一年，点击也走 `selectPeriod` 下钻，与方格图
             交互对齐；日粒度是叶子，不传 `drillable`（柱不可点）。`drillable` 取
             `canDrill`：宿主排掉了下一档粒度时（如 #2033 的右卡排掉日粒度），柱体与
             柱下提示一并撤掉，免得留一个「可点却没反应」的假 affordance。 -->
        <PnlCalendarBars
          v-else
          :days="cal.series?.days ?? []"
          :periods="cal.series?.periods ?? []"
          :range-label="cal.rangeLabel"
          :total="cal.series?.month_total ?? 0"
          :range-rate="cal.series?.range_rate ?? null"
          :mode="cal.valueMode"
          :drillable="cal.canDrill"
          @select="cal.selectPeriod"
        />

        <!-- ===== 合计行：一行小字，不占纵向空间（Voice & Content规范） ===== -->
        <PnlCalendarSummary
          :range-label="cal.rangeLabel"
          :total="cal.series?.month_total ?? null"
          :range-rate="cal.series?.range_rate ?? null"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import SectionHeader from "@/components/SectionHeader/index.vue";
import PnlCalendarGrid from "./PnlCalendarGrid.vue";
import PnlCalendarPeriodGrid from "./PnlCalendarPeriodGrid.vue";
import PnlCalendarBars from "./PnlCalendarBars.vue";
import PnlCalendarCaliberTip from "./PnlCalendarCaliberTip.vue";
import PnlCalendarActionBar from "./PnlCalendarActionBar.vue";
import PnlCalendarPlaceholder from "./PnlCalendarPlaceholder.vue";
import PnlCalendarSummary from "./PnlCalendarSummary.vue";
import { usePnlCalendarData } from "./usePnlCalendarData";
import type { PnlCalendarDay, PnlCalendarGranularity } from "@/api/summary";

defineOptions({ name: "PnlCalendar" });

const props = withDefaults(
  defineProps<{
    /** 账户ID：不传=家庭级，传=该账户级（账户维度天然支持，见设计文档 §3） */
    ledgerId?: number;
    /**
     * 宿主是否自带标题行（#2050）。
     *
     * PnlCalendar 的三处容器——投资概览第三排、资产总览右卡、账户详情——共用同一份
     * 口径。资产总览那处外面套了卡片标题（`OverviewSummaryCard` 必须自己画 `<h3>`，
     * 因为它要在「资产大类 / 收益日历」两态之间变，还挂着返回开关）。
     *
     * 旧 `hideTitle` 只抑制 `<h2>` 文字，`#info` 口径图标仍独占一行（窄容器下被控件行
     * 挤断后只剩残影）。`hostHeader` 模式下本组件**完全不画 `SectionHeader`**——标题、
     * 口径图标、控件三者由宿主一行排开，宿主用 `PnlCalendarCaliberIcon` 画图标。
     * 另两处不传即为 `false`，行为与改动前完全一致。
     */
    hostHeader?: boolean;
    /**
     * 本宿主允许的粒度档位（#2033）；不传 = 三档全开（welcome / 账户详情）。
     *
     * **日粒度的家在投资概览页**（welcome 第三排的满宽日历）：那是唯一容得下
     * 「一屏 5 列 × 数行」日历的地方。资产总览右卡是**与左卡并排的等高兄弟容器**
     * （卡片体锁死 280px），日粒度在那里既排不下也读不清，故由宿主传
     * `["month", "year"]` 把它摘掉——同时**不提供任何入口**（没有「展开/查看大图」），
     * 日粒度的需求去 welcome 即可，二者各归其位。
     *
     * 只挡控件排不够：方格与柱体的点击下钻也会一路走到日粒度，
     * 所以 `selectPeriod` 与 `canDrill` 也读同一份约束（见 `helpers.nextGranularity`）。
     */
    granularities?: readonly PnlCalendarGranularity[];
  }>(),
  { ledgerId: undefined, hostHeader: false }
);

const emit = defineEmits<{
  (e: "select-day", payload: { date: string; day: PnlCalendarDay }): void;
}>();
void emit; // 预留的「点某天看明细」事件，当前尚无消费方；保留契约避免破坏容器

// 状态机整体搬进 composable（见文件头），此处只把 props 作为 getter 交进去：
// 传 getter 而不是传值，才能在宿主改 `ledgerId` / `granularities` 时触发重取。
const cal = usePnlCalendarData({
  ledgerId: () => props.ledgerId,
  granularities: () => props.granularities
});

defineExpose({ reload: cal.load });
</script>

<style lang="scss" scoped>
.pnl-calendar {
  display: flex;
  flex-direction: column;
  gap: 14px;

  /* #2033：跟随宿主的高度。宿主给了确定高度（资产总览右卡的等高容器，280px）
     这里就是 280px，整列由下方的 body 吃掉剩余空间；宿主高度不定
     （welcome 满宽 / 账户详情半宽）时百分比高度解析为 auto，仍是自然高——
     **高度约束只能由宿主施加**，本组件不自带任何固定高度。 */
  height: 100%;
}

/* 主体区（方格图 / 柱状图 + 合计行）：`flex: 1` 吃掉控件排以外的高度，
   `min-height: 0` 让内部（年格网格外层的滚动容器）真能收缩——没有它，
   flex 项的自动最小尺寸会把内容高度顶回来，装不下时卡片就被撑破而不是内部滚动。 */
.pnl-calendar__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

/* 年视图的区间标签（替代区间导航按钮组：年视图区间固定，按不动的按钮是骗人的）。
   ⚠️ 当前模板里没有 `.pnl-calendar__range` 节点（区间标签已由 `PnlCalendarActionBar`
   自绘）。规则先留着不为别的：删掉它属于「顺手清理」，会让本次纯搬运的等价性核对
   多出一条无法归因的差异；真要删，单独一个 PR 连同类死规则一起清。 */
.pnl-calendar__range {
  font-size: var(--text-label);
  color: var(--text-secondary);
}
</style>
