<script setup lang="ts">
import { computed, toRef } from "vue";
import VChart from "vue-echarts";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import { TREND_VIEW_OPTIONS } from "./trendViewMetrics";
import ProductProfitPanel from "./ProductProfitPanel.vue";
import { useProductTrend } from "../composables/useProductTrend";
import { buildTrendChartOption } from "./trendChartOption";

/**
 * 详情页「走势」区块（#1967 · 设计 §5 B 区块）。
 *
 * 口径与红线：
 * - 区间 `1M/3M/6M/1Y/3Y/5Y`，**默认 3M**（设计 §12 ⑤；3Y/5Y 为 2026-10-17 长区间
 *   补充档——短期收益不代表长期收益）；历史不够长时由 `available_days`
 *   判断并提示收敛，不画一条只有几天的曲线假装是 3M；
 * - **品类差异化**（#1969）：场内有 OHLCV → K 线 + 成交量 + MA5/10/20（口径未复权，
 *   与持仓成本可比）；场外基金只有净值 → 净值线（#2171 起为**累计净值**，
 *   缺失回退单位净值，与业绩卡同源——单位净值遇分红除息跳空是假暴跌）；
 * - 图表颜色一律经 `getCssVar` 取**真实色值**：ECharts 不解析 `var(--x)`，给变量字符串
 *   等于给了一个无效色（旧版 splitLine 的写法就是这么错的，也会让网格看起来发黑发乱）；
 * - 线条**不平滑**：smooth 会画出实际不存在的峰谷，价格序列上属失真；
 * - **无数据就显示空态**，绝不用 mock 顶替（设计 G1 教训）；
 * - 脚注写明「数据日期 · 来源 · 口径」——来源是站点名，不是内部表名（#1969）；
 * - **品类无序列源时整卡不渲染**（#1967 后续）：后端对 manager / portfolio /
 *   无日线的 index 返回 `kind=''` + 空序列，此时渲染出的只有标题的卡片是纯噪声。
 *   走势区块已从最后一屏移回首屏（设计 §5 B 位），这条降级从「脚注」升级为
 *   「区块整体不渲染」（设计 §6 降级规则）。判据取后端 `kind` 而非在前端镜像
 *   一份「哪些品类没序列」的类型清单——后端 `product_trend._NO_SERIES_TYPES`
 *   是权威，前端不复制它。
 *
 * ## 买卖点 / 成本线叠加（#2171）
 *
 * - **叠加层只在折线视图**：买卖点（锚定当日净值 / 收盘价）与成本线（`avg_cost_yuan`）
 *   都与折线同轴可比。成本线**必须**取「元/份」那个字段——取总成本会让曲线被压平
 *   （见 `costSeriesData` 注释）；
 * - **场内提供「K线 / 折线」两个视图**（#2171 后续）：K 线是**未复权价格** + cross tooltip
 *   + 双 grid（量能副图），叠买卖点等于在同图上放第二套坐标语义，故**不往 K 线上硬叠**；
 *   场内要看买卖点就切折线视图（画**收盘价**，与持仓成本同口径），直接复用同一套叠加层与
 *   成本线口径，不新写坐标。三个视图判定（切换器是否可见 / 成交量副图 / 叠加层是否可用）
 *   收口在 `trendViewMetrics`（含单测）；
 * - 买卖点的复盘场景另有更合适的落点：资产复盘页的「调仓时间线」
 *   （`docs/features/asset-review.md` 组件 5，按周期列出每笔买卖 + 卖出的实现盈亏）；
 * - **取色避开 rise/fall**：买卖点不是涨跌语义，红绿会让「我买过」被误读成「涨了」。
 *   蓝（info）三角朝上=买入、橙（warning）三角朝下=卖出、中性灰虚线=成本线——
 *   形状主编码，色弱用户也能分辨；
 * - **低于当时成本线 → 空心**（P1）：当日均价 < 当日最后一笔之前的持仓均价。
 *   低吸 / 割肉一眼可辨，tooltip 附偏离度；首笔前无持仓不判（无参照不下结论）。
 *   不引入第三种颜色——那会和涨跌语义打架；
 * - **同日多笔聚合**为一个点（金额合计 + 笔数），tooltip 显示「N 笔合计」；
 * - **点大小 = 弱金额权重**（#2171 §4.2）：直径 6–16px，`min + (max−min)×√权重`（开方是
 *   刻意的：金额长尾，线性映射会让一笔大额买入把其余点全压成米粒）；权重按本侧当日聚合
 *   金额归一，**点数 > 20 自动压低上限**（不按周/月聚合——那会改变「哪天操作的」这个事实）；
 *   卖点上限再低一档；「统一大小」开关可关掉权重映射。公式与边界住在
 *   `trendMarkerMetrics`（含单测：开方映射 / 分母为 0 不产生 NaN —— NaN 会让 ECharts
 *   **默默不画这个点**，等于把交易记录藏了）；
 * - **成本线前向填充**：非交易日延续前值，首笔交易前为 null 不画，清仓日断在最后一笔；
 * - **「历轮」开关**（P1）：清仓后重建仓的用户可关掉旧轮次，只看最近一轮；
 * - **清仓轮次标记**（P2）：每轮结束（`closed`）在图上画一条**点线**竖线并编号
 *   （「第 N 轮清仓」；只有一轮时只写「清仓」——写「第 1 轮」是噪声）。编号按**全量**
 *   流水算、再按可见范围过滤，否则关掉「历轮」后标签会从第 1 轮重新开始、与实际不符；
 *   逻辑收口在 `trendMarkerMetrics.clearingMarks`（含单测）；
 * - **建仓期区间**（P1）：有流水时区间栏追加「建仓」档——首笔买入日至今，
 *   显式起始日走后端 `start` 参数（档位表达不了因人而异的长度）；
 * - **时间线不分区间**：后端一次返回全量重放结果，前端按当前区间过滤展示；
 * - 拉取失败 / 未持有 → 静默不渲染叠加层，主曲线不受影响（设计 §6）。
 *
 * ## 口径维度：净值 / 业绩（#2454）
 *
 * 走势图原来只有**净值/收盘价**一条线，答的是「现在多少钱」；用户要的**业绩走势**
 * 答的是「这段时间赚了多少」——后者从对前者的**纯派生**算出，不新开接口：
 *
 * - **基准 = 窗口首日**（不是成立以来）：用户问的是「这段」时间。成立以来收益是
 *   业绩卡的口径，同页不造第二个数字（#2171 决策）；
 * - 计算收口在 `trendBasisMetrics`（含单测）：首日恒 0、非有限值回落 0
 *   （ECharts 遇 NaN 会**默默跳过该点**，等于藏数据——`trendMarkerMetrics` 同款教训）；
 * - **业绩口径强制折线**：K 线画 OHLC 价格，没有「收益率 K 线」。合成判据是
 *   `basis === 'nav' && effectiveUseCandle(...)`——「实际在画什么」而不是
 *   「切换器选中什么」（#2453 纪律，选中值在切换器不渲染时没有语义）；
 * - 业绩口径下叠加层**重新锚定**到收益率空间（买卖点 y、成本线都按同一基准换算），
 *   tooltip 主行给 `收益率%（当日净值/成本 价格）`——只看 % 不知道当时多少钱；
 * - 画一条 **0% 基准线**：曲线本身从 0 出发，但没有这条线时「高于/低于基准」
 *  要靠眼估刻度；红涨绿跌沿用中国市场惯例（CHART_TOKENS.rise/fall）。
 *
 * ## 累计收益面板（P1，见 ProductProfitPanel.vue）
 *
 * 与叠加层共用同一次时间线请求（detail 层不重复取数）：累计已实现盈亏 +
 * 金额 / 收益率切换 + 紧凑统计条。曲线**全程展示不随区间缩放**——区间是看净值
 * 波动的窗口，不是看盈亏历史的窗口。
 */
const props = defineProps<{
  symbol: string;
  /** 品类：由 #1963 resolve 判定后回传，后端据此选收盘价 / 净值口径 */
  assetType?: string;
  /** 当前家庭是否持有该产品（详情页 resolve 回传）。仅持有时拉交易时间线——
      流水是私有数据，未持有用户发请求只会拿到空结构，还多一次往返（#2104 同款教训）。 */
  hasPosition?: boolean;
}>();

// 状态与派生全部来自 useProductTrend；这里解构成同名变量，模板逐字不变（#980 拆分纪律）。
const {
  range,
  rangeOptions,
  loading,
  failed,
  trend,
  noSeries,
  hasData,
  isCandle,
  candleView,
  basis,
  basisOptions,
  canToggleView,
  showMarkers,
  unifiedSize,
  showHistoryRounds,
  hasHistoryRounds,
  hasMarkers,
  markersActive,
  tradesHiddenByView,
  hasTrades,
  spanNotice,
  timeline,
  themeTick,
  hasVolume,
  candleCloses,
  candleData,
  returnSeries,
  useCandle,
  clearingMarksList,
  costPlotSeries,
  costSeriesData,
  sizedMarkers
} = useProductTrend({
  symbol: toRef(props, "symbol"),
  hasPosition: toRef(props, "hasPosition"),
  assetType: toRef(props, "assetType")
});

const chartOption = computed(() =>
  buildTrendChartOption({
    themeTick,
    trend,
    hasVolume,
    candleCloses,
    candleData,
    basis,
    returnSeries,
    isCandle,
    useCandle,
    markersActive,
    clearingMarksList,
    costPlotSeries,
    costSeriesData,
    sizedMarkers,
    assetType: props.assetType
  })
);
</script>

<template>
  <CardBlock v-if="!noSeries" class="trend-section">
    <SectionHeader title="走势">
      <template #action>
        <!-- ⚠️ 必须自己套一层 flex-wrap 容器（#2039）：SectionHeader 的 action 槽会随窄容器
             收缩，但**只有调用方内层是可折行容器时才会折行**——否则多枚控件直接溢出卡片、
             叠到左侧 ⓘ 上。本区现在是「区间 + 视图 + 3 个复选框」共 5 枚，必须折行。 -->
        <div class="trend-section__actions">
          <SegmentedControl
            v-model="range"
            :options="rangeOptions"
            size="small"
            ariaLabel="切换走势区间"
          />
          <!-- 口径切换（#2454）：净值/价格 vs 业绩（区间累计收益率）。场内外都给——
               「现在多少钱」与「这段时间赚了多少」是两个问题，后者由业绩线答。
               与视图切换**正交**：口径决定 y 轴画什么，视图决定用什么画。 -->
          <SegmentedControl
            v-model="basis"
            :options="basisOptions"
            size="small"
            ariaLabel="切换走势口径"
          />
          <!-- 场内视图切换（#2171 后续）：K 线 / 折线。折线视图让买卖点与成本线能叠上来
               （它们都是「元/股」日序列，只能与折线同轴）；场外只有一条线，不显示该切换器。
               **业绩口径下同样隐藏**（canToggleView 已含 basis 判定）——K 线没有收益率
               画法，留一个点了没反应的选项是假可操作性（#2453 同款纪律）。 -->
          <SegmentedControl
            v-if="canToggleView"
            v-model="candleView"
            :options="TREND_VIEW_OPTIONS"
            size="small"
            ariaLabel="切换走势视图"
          />
          <!-- 买卖点 / 成本线开关（#2171）：有交易点才可开；关掉后只剩曲线。
               默认开——「我买在了哪」是买方核心诉求；信息过载的用户可自行关闭。 -->
          <el-checkbox v-if="hasMarkers" v-model="showMarkers" size="small">
            买卖点
          </el-checkbox>
          <!-- 统一大小（#2171 §4.2）：默认关 = 弱金额权重（看得出大额买入）；
               只想看「我在哪买过」的用户打开它，曲线立刻安静下来。 -->
          <el-checkbox
            v-if="hasMarkers && showMarkers"
            v-model="unifiedSize"
            size="small"
          >
            统一大小
          </el-checkbox>
          <!-- 历轮买卖（#2171 P1）：仅清仓后重建仓的用户可见。关掉只看最近一轮——
               旧轮次的点会让「现在的成本线」难以认读。 -->
          <el-checkbox
            v-if="hasHistoryRounds && showMarkers"
            v-model="showHistoryRounds"
            size="small"
          >
            历轮
          </el-checkbox>
        </div>
      </template>
    </SectionHeader>

    <p v-if="loading" class="trend-section__hint">正在读取走势…</p>

    <p v-else-if="failed" class="trend-section__hint">
      走势读取失败，可稍后重试
    </p>

    <p v-else-if="!hasData" class="trend-section__hint">暂无该区间的历史数据</p>

    <template v-else>
      <v-chart
        :option="chartOption"
        :autoresize="true"
        class="trend-section__chart"
      />
      <p v-if="spanNotice" class="trend-section__hint">{{ spanNotice }}</p>
      <!-- 买卖点开关被视图挡住时给一句明话（#2453）：开关不渲染 + 一句话解释，
           比留一个点了没反应的勾选框诚实，也让「折线视图为什么存在」有答案。 -->
      <p v-if="tradesHiddenByView" class="trend-section__hint">
        买卖点与成本线在「折线」视图中叠加显示
      </p>
      <!-- 来源说「哪个网站」，口径说「怎么算的」——后端分开给，前端只排版，
           不在这里推断「close 就等于前复权」（#1969）。
           空心买卖点（#2171 P1）：成交价低于当时持仓成本——低吸 / 割肉。 -->
      <p class="trend-section__footnote">
        数据日期：{{ trend?.dates?.[0] }} 至
        {{ trend?.dates?.[trend.dates.length - 1] }}
        <template v-if="trend?.source">
          · 数据来源：{{ trend.source }}（{{ trend.basis }}）
        </template>
        <!-- 业绩口径（#2454）：口径说明——基准是区间首日（不是成立以来），
             与「这段时间赚了多少」这个问题对齐；成立以来收益归业绩卡，不重复造。 -->
        <template v-if="basis === 'return'">
          · 业绩以区间首日{{ isCandle ? "收盘价" : "净值" }}为基准
        </template>
        <template v-if="hasMarkers"> · 空心△ = 低于当时成本</template>
      </p>
    </template>

    <!-- 累计收益面板（#2171 P1）：全程累计已实现 + 紧凑统计条。
         有流水才渲染；数据来自与叠加层同一次时间线请求，不重复取数。 -->
    <ProductProfitPanel v-if="hasTrades" :timeline="timeline" />
  </CardBlock>
</template>

<style scoped>
.trend-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.trend-section__chart {
  width: 100%;

  /* K 线格 + 量能格叠放（见 chartOption 的 grid 高度），故比单线图高一截 */
  height: 300px;
}

.trend-section__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.trend-section__footnote {
  margin: 0;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* action 槽的内层容器：**必须可折行**（#2039）。SectionHeader 的槽会收缩，但只有在
   调用方内层 `flex-wrap: wrap` 时才折行——否则区间/视图/复选框一排直接溢出卡片。
   `justify-content: flex-end` 让折行后仍贴右对齐，宽屏下与折行前逐像素一致。 */
.trend-section__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2, 8px);
  align-items: center;
  justify-content: flex-end;
}
</style>
