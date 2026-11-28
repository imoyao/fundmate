<template>
  <!-- 账户信息头部 -->
  <div class="mb-6 flex items-center justify-between">
    <div>
      <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">
        {{ p.accountName }}
      </h2>
      <div class="flex items-center gap-2 mt-1">
        <el-tag size="small" type="info" round>{{ p.subTitle }}</el-tag>
        <template v-if="p.summaryData?.portfolio_name">
          <span class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
            · 组合: {{ p.summaryData.portfolio_name }}</span
          >
        </template>
      </div>
    </div>
  </div>

  <!-- 温柔提醒（#1133 §4）：中性信息色、拟人化、非阻断；可选「去对账/忽略」，绝不强制。
       #2730 起壳由 SoftBanner 的 info 档承担；`role="note"` **显式传入** —— 组件默认按色族
       推导（info→status 礼貌播报 / warning·danger→alert 打断播报），而这里原文就是
       `role="note"` 的静态注记（不排队播报），迁入时不能被无意识升格成 live region。 -->
  <transition name="el-fade-in">
    <SoftBanner
      v-if="p.visibleConsistencyItems.length > 0"
      class="soft-reconcile-banner"
      variant="info"
      role="note"
      icon="ep:info-filled"
    >
      <p class="soft-reconcile-banner__title">
        这本账本的持仓快照截至
        {{
          p.visibleConsistencyItems[0].snapshot_date
        }}，快照日之后仍有交易记录；如与流水对不上，请去对账中心核对是否需要补录。
      </p>
      <p class="soft-reconcile-banner__detail">
        共
        {{ p.visibleConsistencyItems.length }}
        笔持仓可能滞后，去对账中心可统一核对。
      </p>
      <template #actions>
        <el-button size="small" type="primary" plain @click="p.goReconcile">
          去对账
        </el-button>
        <el-button size="small" text @click="p.dismissAllConsistency">
          忽略
        </el-button>
      </template>
    </SoftBanner>
  </transition>

  <!-- 账本概览（对齐「家庭资产看板」范式：SectionHeader + CardBlock，左指标 / 右资产构成）。
       #2739：锚点挂在标题行上（SectionHeader 单根 ⇒ id 经 fallthrough 落下），
       与本页其余锚点同一手法——锚点 = 区块标题行的顶边。 -->
  <SectionHeader id="nav-overview" title="账本概览" />
  <CardBlock class="mb-6">
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
      <!-- 左栏：核心指标（总资产 + 持仓盈亏 / 累计盈亏 / 持仓与余额） -->
      <div
        :class="showComposition ? 'lg:col-span-7' : 'lg:col-span-12'"
        class="flex flex-col gap-5"
      >
        <!-- 总资产 -->
        <div class="overview-hero">
          <p
            class="text-sm mb-2"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          >
            总资产
          </p>
          <div class="flex items-baseline gap-2">
            <MoneyDisplay
              :value="p.summaryData?.total_market_value || 0"
              size="hero"
              :show-sign="false"
            />
            <span
              class="text-xl font-medium"
              :style="{ color: 'var(--text-secondary)' }"
              >元</span
            >
          </div>
        </div>

        <!-- 指标格（2026-11-15 收敛）：原来 8 格是 8 段复制粘贴，其中常年有 3~4 格
             是 `--`（近 90 天 / 基准同期 / 超额收益 / 资金余额），空占两行高度却什么
             都没说。现在由 `metrics` 数组驱动：值为 null 的条目**整个不生成**，
             说明性微文案改走 `title`（悬浮可见），不再占第二行版面。
             每格带 `data-metric`，读屏、e2e 与 Agent 按语义定位，不依赖文案与位置。 -->
        <div
          class="overview-metrics"
          :style="{
            borderTop: '1px solid var(--border-light)',
            '--metrics-cols': metricColumns
          }"
          data-region="overview-metrics"
        >
          <!-- 持仓盈亏固定第一格（最该被先看到）；累计盈亏 / 当日收益各自带
               口径与「无此字段就不渲染」的逻辑，仍是独立组件。
               #3222：三者都是净值型指标，实物资产（property）账户没有盈亏口径，
               整组不渲染（isInvestment）。 -->
          <div
            v-if="isInvestment"
            class="flex flex-col"
            data-metric="position-pnl"
          >
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >持仓盈亏</span
            >
            <MoneyDisplay :value="p.summaryData?.position_pnl || 0" size="md" />
          </div>
          <LedgerCumulativePnlMetric
            v-if="isInvestment"
            :value="p.summaryData?.total_pnl"
          />
          <LedgerTodayPnlMetric v-if="isInvestment" :data="p.todayPnlData" />

          <div
            v-for="m in metrics"
            :key="m.key"
            class="flex flex-col"
            :data-metric="m.key"
          >
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              :title="m.hint || undefined"
              >{{ m.label }}</span
            >
            <MoneyDisplay
              v-if="m.kind === 'money'"
              :value="m.value"
              size="md"
              :show-sign="!!m.signed"
              :auto-color="!!m.signed"
              :custom-color="m.danger ? 'var(--color-danger)' : undefined"
            />
            <!-- 这两个分支此前是 text-lg(18px) + font-semibold，而金额格是
                 MoneyDisplay md(16px)：同一行三种字号，数字基线互相错开。
                 2026-11-15 统一到 --text-body，只靠颜色区分涨跌。 -->
            <RiseFallText v-else-if="m.kind === 'rate'" :value="m.value" />
            <span v-else class="overview-metrics__value">{{ m.value }} 项</span>
          </div>
        </div>
      </div>

      <!-- 右栏：资产构成分布（仅股票 / 基金 / 信用账户，对齐看板饼图） -->
      <!-- 栏间分割线走全局工具类 `.soft-col-divider`（style/index.scss）：
           自带 24px 内边距、且仅在 lg 及以上出现——原先内联 borderLeft 既贴文字，
           又在 lg 以下两栏堆叠时留一条孤零零的竖线。 -->
      <div
        v-if="showComposition"
        class="lg:col-span-5 flex flex-col items-center justify-center h-full soft-col-divider"
        data-region="composition"
      >
        <div class="w-full flex justify-between items-center mb-4">
          <span
            class="font-bold text-sm"
            :style="{ color: 'var(--text-secondary)' }"
            >资产构成分布</span
          >
        </div>
        <AssetAllocationDonut
          :data="compositionSlices"
          :color-map="p.compositionColorMap"
          :show-legend="true"
        />
      </div>
    </div>
  </CardBlock>

  <!-- #2155 / CNB #479：账外类现金出口。
       它必须**独立成块、并列展示**，不能并进上面的环形图：环形图两片是
       「持仓市值的划分」（合计 = 总资产），账外类现金不建持仓、不在其中
       （并进去会重演 #1606 的「投资资产 -63.2%」负数 bug，口径解耦见 D59）。
       #3222：区块可见性收口到 ledgerDetailSections——property（实物资产）没有
       「类现金」概念，整块不渲染（showCashLike）。
       #2739：anchor-id 让本块在有内容时挂上页内导航锚点（整块不渲染时
       锚点随之消失，导航项不留死链）。 -->
  <LedgerCashLikeCard
    v-if="showCashLike"
    anchor-id="nav-cash-like"
    :summary="p.summaryData"
    :ledger-id="p.ledgerIdNum"
    @saved="p.loadSummary"
  />

  <!-- #3222：实物资产明细（property 专属）。实物不进 positions、只进 assets，
       详情页必须有地方看到「这套房产值多少钱、有几套」。 -->
  <LedgerAssetList
    v-if="showAssetList"
    anchor-id="nav-asset-list"
    :ledger-id="p.ledgerIdNum"
  />

  <!-- #1812：收益日历已落地（账户级，传 ledgerId 走该账户的 as-of 派生序列）。
       与 welcome 第三排 / panorama「资产大类 ⇄ 收益日历」原地切换是**同一组件的三处容器**，
       口径唯一；#1925 起三处都带日 / 月 / 年粒度切换。
       #3222：净值型投资账户专属，property / bank 整块不渲染。
       #2739：id 经 fallthrough 落在面板根（单根元素）＝ 锚点即标题行顶边。 -->
  <div v-if="showPnlSections" class="mb-6">
    <PnlCalendar id="nav-calendar" :ledger-id="p.ledgerIdNum" />
  </div>

  <!-- #2135：收益归因（区间逐品种 / 大类贡献）——复用 pnl 引擎唯一盈亏口径，
       Σ品种 ≡ 同窗收益日历月合计由后端构造保证，前端只展示。
       #3222：净值型投资账户专属。
       #2739：PnlAttribution 是多根组件（吃不到父级 fallthrough），故由调用方
       包一层 div 承接锚点（与组合详情页同一手法）。 -->
  <div v-if="showPnlSections" id="nav-attribution">
    <PnlAttribution :ledger-id="p.ledgerIdNum" />
  </div>

  <!-- #2739：账户深度分析（持仓结构 / 集中度 + 持仓穿透 / 行业分布）。
       这两项能力早已上线（#2617 / #870 + #2595），原先此处是一块写着
       「规划中，敬请期待」的占位卡——那是在把**已存在**的功能说成不存在。
       组件与端点现成、口径与组合详情页 / 复盘页结构区同源，本页只补它独缺
       的这两块，不搬复盘页其余块（详见 docs/spec/account-detail-depth-analysis.md）。
       **必须显式传账户口径**：不传 = 全家庭档，会显示别的账户的数据；
       未归置持仓伪账户没有数字账户 id，整块不展示（与资金流动同一处置）。 -->
  <LedgerDepthAnalysis v-if="showDepthAnalysis" :ledger-id="p.ledgerIdNum" />
</template>

<script setup lang="ts">
import { computed, reactive, toRef } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import PnlCalendar from "@/components/PnlCalendar/index.vue";
import PnlAttribution from "@/components/PnlAttribution/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";
import LedgerCashLikeCard from "./LedgerCashLikeCard.vue";
import LedgerTodayPnlMetric from "./LedgerTodayPnlMetric.vue";
import LedgerCumulativePnlMetric from "./LedgerCumulativePnlMetric.vue";
import LedgerDepthAnalysis from "./LedgerDepthAnalysis.vue";
import LedgerAssetList from "./LedgerAssetList.vue";
import type { useLedgerDetailPage } from "../composables/useLedgerDetailPage";
import { useLedgerSections } from "../composables/useLedgerSections";
import { useBenchmarkExcess } from "../composables/useBenchmarkExcess";
import { isSectionVisible } from "@/composables/ledger/ledgerDetailSections";
import {
  buildOverviewMetrics,
  type MetricCell
} from "../composables/overviewMetrics";

defineOptions({ name: "LedgerDetailOverview" });

// #980 P1-C 拆分自 detail.vue：账户信息头 + 温柔提醒横幅 + 账本概览区。
// 状态单体经 page prop 注入，p. 前缀替换与拆分前的绑定表达式一一对应。
const props = defineProps<{ page: ReturnType<typeof useLedgerDetailPage> }>();
const p = reactive(props.page);

// 区块可见性（#3222）：从 ledgerDetailSections 清单派生，见 useLedgerSections。
// `p` 是 reactive 代理，`p.summaryData` / `p.ledgerIdNum` 已被解包成值，
// 用 toRef 取回 Ref 再传（composable 需要响应式源，不是一次性快照）。
const { isInvestment, showAssetList, showCashLike, showPnlSections } =
  useLedgerSections(toRef(p, "summaryData"));

// 深度分析（#2739）：口径必须本账户——`ledgerIdNum` 解不出来时整块不渲染，
// 否则面板退化成「全家庭」档却写着「账户」口径。这条前提是页面特有，故留在
// 本组件（守卫 ledgerDepthAnalysisGuard 钉住它不许下沉/丢失）。
const showDepthAnalysis = computed(
  () =>
    p.ledgerIdNum != null &&
    isSectionVisible("depthAnalysis", p.summaryData?.ledger_type)
);

// ---------- 概览指标格（2026-11-15 数据驱动）----------
/** 组装逻辑在 `../composables/overviewMetrics.ts`（页面规模门禁 400 行）。 */
/**
 * 指标格实际渲染的格数（用于决定列数）。
 *
 * 三个来源各自可能不渲染：持仓盈亏 / 累计 / 当日只在投资账户（isInvestment）
 * 时出现、`metrics` 已经在组装时过滤过空值。格数浮动，写死列数就会出现
 * 「一行 4 格 + 第二行孤零零 1 格」（2026-11-15 截图实测：5 格 / 4 列）。
 */
const metricCellCount = computed(
  () =>
    (isInvestment.value ? 1 : 0) +
    (isInvestment.value && p.summaryData?.total_pnl != null ? 1 : 0) +
    (isInvestment.value && p.todayPnlData?.total_pnl != null ? 1 : 0) +
    metrics.value.length
);

/**
 * 列数：够一行就一行，多了折成两行且两行等长（7 格 → 4 + 3，不是 5 + 2，
 * 更不是 4 + 1）。上限 5 列——再宽每个格子都不到 170px，数字会挤。
 */
const metricColumns = computed(() => {
  const n = metricCellCount.value;
  return n <= 4 ? n : Math.min(5, Math.ceil(n / 2));
});

const metrics = computed<MetricCell[]>(() =>
  buildOverviewMetrics({
    summary: p.summaryData ?? null,
    moneyFundIncome: p.moneyFundData?.today_income ?? null,
    rangeRate: rangeRate.value,
    benchmarkReturn: benchReturn.value,
    excessReturn: excessReturn.value,
    excessHint: excessHint.value
  })
);

/**
 * 资产构成是否有「可画」的分布。
 *
 * 单扇区（100% 一个分类）画出来就是一个满圈红环——它没说任何事，还占掉
 * 5/12 宽、426px 高（实测账户 id=12/13 都是这种形态）。此时不画图，
 * 让指标区占满整行。
 */
const compositionSlices = computed(() =>
  (p.compositionData ?? []).filter(d => Number(d.value) > 0)
);
const showComposition = computed(
  () => p.isCompositionLedger && compositionSlices.value.length > 1
);

// ---------- #2134：近 90 天区间收益 vs 基准（缺数据诚实降级 null → 模板「--」）----------
// 取数 + 派生下沉到 useBenchmarkExcess（页面规模门禁），页面只消费四个降级字段。
const { rangeRate, benchReturn, excessReturn, excessHint } = useBenchmarkExcess(
  toRef(p, "ledgerIdNum"),
  toRef(p, "ledgerId")
);
</script>

<style scoped lang="scss">
@use "@/style/breakpoints" as bp;

/* 概览指标格（2026-11-15）：格数随数据在 3~7 之间浮动（无值的指标不生成），
   写死 4 列就会出现「第一行 4 格 + 第二行孤零零 1 格」的豁口。
   `auto-fit` + `minmax` 让轨道数跟着格数走，且空轨道会塌缩——几格都能铺满一行。 */
.overview-metrics {
  display: grid;
  grid-template-columns: repeat(var(--metrics-cols, 4), minmax(0, 1fr));
  gap: var(--space-5) var(--space-compact);
  padding-top: var(--space-5);

  /* 窄屏忽略动态列数：先把 5 列压成 3 列，手机再压成 2 列（与 Tailwind 断点同源）。 */
  @include bp.below("lg") {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  @include bp.below("sm") {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* 「N 项」这类计数格：字号跟随金额格（--text-body），只有颜色是正文色。 */
.overview-metrics__value {
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--text-primary);
}

/* 手机端总资产必须缩字（2026-11-15 实测）：hero 档 57px 下
   「¥1,003,546.47」在 390px 视口里被卡片右缘裁掉最后两位——金额被切掉
   比字号小更难接受。`.number` 自带 font-size，两处一起改才生效。
   用 --text-display（32px）而不是裸 px：stylelint 只认令牌（同为 32px）。 */
@include bp.below("sm") {
  /* 覆盖令牌而不是写 font-size：`.money-display.size-hero .number` 自带
     `font-size: var(--text-hero, 57px)`，从祖先改这个自定义属性，父子两处
     一起缩，且不跟组件内的 scoped 规则拼优先级。 */
  .overview-hero {
    --text-hero: var(--text-display);
  }
}

/* 温柔提醒 banner（#1133 §4）：中性信息色，非涨跌色 / 非危险红；轻量、不制造心理压力。
   #2730 起壳由 SoftBanner info 档承担，此处只留两级正文排版。
   已删除的本地壳：display/gap/align-items/padding/margin/background/border/border-radius
   以及 `.soft-reconcile-banner__icon` / `__body` / `__actions`（图标位与动作区由组件提供）。
   随壳一起去掉的是 `border-left: 3px solid var(--el-color-info)` —— 判为**冗余装饰**：
   它的语义（中性信息）与 info 档图标 `--color-info-ink` 完全重合，且 `--el-color-info`
   是 Element Plus 直调（tech-debt 明令的颜色直调），链路里唯一用处就是这道 3px 条。
   不加 `accent` prop 的理由见 docs/spec/soft-banner.md §3（单消费方不值得把壳变成可拼装结构）。 */
.soft-reconcile-banner__title {
  margin: 0;
  font-size: var(--text-small);
  line-height: 22px;
  color: var(--text-primary);
}

.soft-reconcile-banner__detail {
  margin: 4px 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
