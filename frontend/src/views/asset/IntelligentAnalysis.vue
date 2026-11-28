<!--
  复盘（时间维度的表现）—— 原「智能分析」，#2150 重新定义定位。

  一句话定位：**以「时间维度上的表现」为骨架，结构区只放解释表现的那几面。**
  无数据源的推测性面板（收益预测 / AI 配置建议 / 事件预警）一律不上屏——
  账本软件只算已发生的账，不编未来的数。

  ── 完整定位、与 welcome / panorama 的分工表、#2150 删掉了哪四块、以及
     「结构问题归谁」的三行判据，全部在
     `docs/working-notes/analysis-page-redesign-2026-11-27.md` §5.3。
     改这一页之前请先读那一节：本页的四条去重判据由
     `scripts/tests/welcome_structure_dedup.test.js` 钉住，别顺手把
     `category_distribution` 或 `getPositionGroups` 引回来。─────────────

  ── 独占项（本页存在的理由）──────────────────────────────────────
  **资产净值走势**：welcome 已明确让出（`WelcomeAssetBoard.vue:131-138`），
  panorama 只用 snapshots 取最新环比/同比、**不画曲线**。全站唯一。

  ── 2026-11-28 页面合并（P3-C）────────────────────────────────────
  原「持仓分析」页（`/asset/position-analysis`）的区间表现 / 收益日历 / 收益归因
  三块迁入本页，旧路由保留为重定向；结构区**只留本页这一份**（两页此前各有一份
  同源同组件）。档位仍只开家庭 / 账户两档——组合档的四个后端空洞留到三期。
-->
<template>
  <div
    class="analysis-page min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 页头必须挂在**块级**根节点下，不能塞进 .analysis-shell：后者是 flex 列容器，
         而 .page-header 自带 `margin: 0 auto`——交叉轴上的 auto 外边距会让
         `align-items: stretch` 失效，页头收缩成内容宽（实测 565px / 容器 1264px）
         并被 auto 外边距居中，标题与下方小节左边缘错开 349px，「更新时间」胶囊
         也浮在页面中部。与 dividends / TransactionList 的「页头在外、shell 只包内容」
         口径一致（#1501 / #1506）。 -->
    <PageHeaderBar
      title="投资复盘"
      subtitle="时间维度上的表现：净值怎么走、收益从哪来"
      :updated-at="updatedAtLabel"
    >
      <template #action>
        <el-button :loading="loading" @click="reloadAll">
          <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新数据
        </el-button>
      </template>
    </PageHeaderBar>

    <div class="analysis-shell">
      <!-- 口径切换：**页级**主控（#3287），不是某个区块的控件——它决定整页 7 段
           数据的作用域，切一次全页重取。
           为什么吸附：滚到第 5 段时用户已经不记得选的是哪个账户，而口径错了整页
           都是错的。「页头 action 槽」放不下这个要求——页头一滚就没了。
           为什么是 shell 的第一个子元素：shell 用 `gap` 排子元素，gap **不作用于
           第一个子元素的上方**；若放在中间，`top: 0` 停住时上方会留一条 48px 的
           缝，页面内容从缝里穿过去（实测很显眼）。 -->
      <div v-if="scopeKinds.length > 1" class="analysis-scope">
        <ScopeBar
          :id="scopeId"
          :kind="scopeKind"
          :kinds="scopeKinds"
          :ledgers="ledgerOptions"
          :loading="ledgerLoading"
          :hint="scopeHint"
          @update:kind="setScopeKind"
          @update:id="setScopeId"
        />
      </div>

      <!-- 幽灵重复告警：属对账范畴（#2151 迁往对账中心「跨账本重复交易」域）。
           域 D 存在之前留在本页，因为「异常要看得见」优先于「归属洁癖」。 -->
      <GhostDuplicateBanner />

      <!-- 结构拆解不在这里：指一条明路，而不是让用户自己猜「想看结构该去哪」。
         #2150 删掉与资产总览重复的四块后，页面从「堆砌」变成「单一主题」，
         此条链接就是那次删除的可见交代。 -->
      <p
        class="analysis-crosslink"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        大类构成与账户拆解仍在<el-button
          text
          size="small"
          @click="router.push('/panorama')"
          >资产总览</el-button
        >；下方的结构区只放与「表现从哪来」直接相关的那几面（钱压在哪些品种 /
        哪些行业 / 什么风格）。
      </p>

      <!-- 页内导航：<xl 顶部锚点胶囊；xl+ 由正文右侧的目录 rail（PageToc）接管。
         条目由 usePageNav 按 DOM 里真实渲染的 nav-* 锚点动态生成，不留死链。 -->
      <PageNav
        v-if="navItems.length > 1"
        :items="navItems"
        :active-id="navActiveId"
        @navigate="goToNavSection"
      />

      <!-- #2156 铁律 1「结构一致」：删掉风险热力图与 #2150 重复四块后，真实区块为
         「收益概览 / 资产净值走势 / 资金流动 / 清仓复盘 / 浮亏回本 / 持仓结构 / 货基收益」
         七段（#2131 清仓周期复盘含表格，故 table-rows=5 与真实行数匹配；浮亏回本无浮亏时
         整块不渲染、结构区三块各有空态，骨架屏不随它们增减）。
         顺序 = 信息重要性：数字 → 数字的形状 → 钱的进出（曲线的台阶） → 单笔已实现结果 →
         未实现的风险 → 风险来自哪（结构）→ 口径补充项。 -->
      <PageSkeleton
        v-if="initialLoading"
        :cards="3"
        :chart-cols="2"
        :table-rows="5"
      />

      <!-- 切到账户档但还没选账户：**一个区块都不渲染**。
           给面板传 `undefined` 等于家庭级（`{}` 在面板里就是「家庭」），于是「单账户」
           标签下会摆着全家庭的钱——本次改造要消灭的正是这种静默错口径。
           宁可让人对着一句话，也不要让人对着错数。 -->
      <p v-else-if="!scopeReady" class="analysis-scope-empty">
        在上方选择一个账户后开始分析
      </p>

      <div v-else class="analysis-body">
        <div ref="pageMain" class="analysis-main">
          <!-- 收益概览（真实 XIRR，无预测）#871：拆为 ReturnOverviewSection，
              自含取数与口径切换（#980）；父页持 ref 供「刷新数据」联动 -->
          <ReturnOverviewSection
            id="nav-overview"
            ref="returnOverview"
            :ledger-id="scopeProps.ledgerId"
          />

          <!-- 区间表现 vs 基准（#2134，2026-11-28 自持仓分析页迁入）：与收益概览同为
               「赚了多少」的数字，紧跟其后；四卡数据全由后端算，前端只做文案与配色。 -->
          <ExcessSection ref="excess" :ledger-id="scopeProps.ledgerId" />

          <!-- 资产净值走势：**紧跟收益数字卡**（#8）。原先排在整页最末，被 334 行
             清仓表压到第 20 屏——曲线是那 5 张卡片的「形状」，把结论与结论的形状
             隔开 17 000px，等于让用户用滚动条自己做关联。
             2026-11-28 拆为 NetWorthTrendSection：口径切换器要进页面，父页已顶在
             400 行闸门上；拆走后曲线自己管取数 / 绘图 / 切档重取，父页只管位置。 -->
          <NetWorthTrendSection
            id="nav-net-worth"
            ref="netWorth"
            :ledger-id="scopeProps.ledgerId"
            @latest-date="latestSnapshotDate = $event"
          />

          <!-- 资金流动（2026-11-27）：紧跟净值走势——曲线的台阶就是入金 / 出金，放下面
               才对得上「这天为什么抬了一截」。`family` = 家庭级（同页统一口径）。
               ⚠️ 本块「净投入」是出入金口径（L1），与上方收益概览那张卡（买入 − 卖出，
               L2）不是同一个数，面板 ⓘ 已写明，别在这里再解释一遍。 -->
          <LazySection anchor-id="nav-cash-flow" :min-height="720">
            <CashFlowPanel
              ref="cashFlow"
              :ledger-id="scopeProps.ledgerId"
              :family="scopeKind === 'family'"
            />
          </LazySection>

          <!-- 收益日历（2026-11-28 自持仓分析页迁入）：日/月/年三视图的盈亏热力图，
               紧接「资金流动」——两者都是「钱按时间怎么分布」，一个看进出、一个看盈亏。
               面板自带 SectionHeader 与口径 ⓘ，此处只挂锚点，不再套一层标题。 -->
          <LazySection anchor-id="nav-calendar" :min-height="400">
            <PnlCalendar :ledger-id="scopeProps.ledgerId" />
          </LazySection>

          <!-- 清仓周期复盘（#2131：已落袋表现的时间维度——与本页「表现从哪来」同主题）。
             自加载自降级：接口失败渲染空态表格，不影响上方 XIRR 与净值走势。 -->
          <LazySection anchor-id="nav-cycles" :min-height="1850">
            <ClearedCyclesSection :ledger-id="scopeProps.ledgerId" />
          </LazySection>
          <!-- 浮亏回本（2026-11-27）：上面三块都是已实现 / 时间维度，这块回答
               「现在亏着的还要涨多少才回本」——收益率答不了（−20% 要涨 25%）。
               放清仓复盘之后：已实现与未实现上下对照，同一屏看完「赚到的」与「欠着的」。 -->
          <BreakEvenSection ref="breakEven" :ledger-id="scopeProps.ledgerId" />

          <!-- 持仓结构（2026-11-27，用户第 9 条）：报「收益由什么构成」，三块面板与
               内部间距收在 AnalysisStructureSection 里，父页只管它在页内的位置。 -->
          <LazySection anchor-id="nav-structure" :min-height="2460">
            <AnalysisStructureSection :ledger-id="scopeProps.ledgerId" />
          </LazySection>

          <!-- 收益归因（#2135，2026-11-28 自持仓分析页迁入）：结构区回答「钱压在哪」，
               归因回答「这些钱各贡献了多少」——同一屏内「分布 → 贡献」，故紧随结构区。
               面板自带 SectionHeader，此处只挂锚点。 -->
          <LazySection anchor-id="nav-attribution" :min-height="780">
            <PnlAttribution :ledger-id="scopeProps.ledgerId" />
          </LazySection>

          <!-- 货币基金收益（#947）：排最后——口径自成一套（万份收益 × 份额）且已计入
               总资产，属「补充解释」，不该占住首屏与 XIRR 抢注意力。
               取数自含（拆出 MoneyFundIncomeSection），父页只经 ref 联动刷新。 -->
          <MoneyFundIncomeSection
            ref="moneyFund"
            :ledger-id="scopeProps.ledgerId"
          />
        </div>

        <!-- xl+ 右目录 rail：与顶部胶囊共用 items/activeId（usePageNav 下发） -->
        <PageToc
          v-if="navItems.length > 1"
          :items="navItems"
          :active-id="navActiveId"
          @navigate="goToNavSection"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import GhostDuplicateBanner from "@/components/GhostDuplicateBanner/index.vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageNav from "@/components/PageNav/index.vue";
import PageToc from "@/components/PageToc/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import CashFlowPanel from "@/components/CashFlowPanel/index.vue";
import LazySection from "@/components/LazySection/index.vue";
import ScopeBar from "@/components/ScopeBar/index.vue";
import PnlCalendar from "@/components/PnlCalendar/index.vue";
import PnlAttribution from "@/components/PnlAttribution/index.vue";
import { useAnalysisPageScope } from "./composables/useAnalysisPageScope";
import ClearedCyclesSection from "@/views/asset/cleared-cycles/ClearedCyclesSection.vue";
import AnalysisStructureSection from "./AnalysisStructureSection.vue";
import NetWorthTrendSection from "./NetWorthTrendSection.vue";
import ReturnOverviewSection from "./ReturnOverviewSection.vue";
import MoneyFundIncomeSection from "./MoneyFundIncomeSection.vue";
import BreakEvenSection from "./BreakEvenSection.vue";
import ExcessSection from "./ExcessSection.vue";
import { usePageNav } from "@/composables/usePageNav";
import { useLazyNav } from "@/composables/useLazyNav";

defineOptions({ name: "AssetAnalysis" });

const router = useRouter();

// 真实数据源：本页只剩「账户列表」（供口径切换器的下拉）；其余 10 个区块全部自含取数
// （收益 / 区间 / 净值 / 资金流 / 日历 / 清仓 / 浮亏 / 结构 / 归因 / 货基），
// 父页只持 ref 做刷新联动。
// 口径主控（档位 / 账户下拉 / 一行说明）收在 composable 里：本页已顶在 400 行闸门上，
// 而这段与页面结构无关（详见 useAnalysisPageScope 文件头）。
const {
  scopeKinds,
  scopeKind,
  scopeId,
  scopeReady,
  scopeProps,
  setScopeKind,
  setScopeId,
  ledgerOptions,
  ledgerLoading,
  scopeHint,
  loadLedgers
} = useAnalysisPageScope();

const initialLoading = ref(true);
const loading = ref(false);

/** 页头「更新时间」：净值区块拆走后由它上报（`@latest-date`），本页不再持有快照对象 */
const latestSnapshotDate = ref("");
const updatedAtLabel = computed(() =>
  latestSnapshotDate.value ? `${latestSnapshotDate.value} 更新` : ""
);

// 页内导航（2026-10-25）：纵向独立区块（收益概览 / 区间表现 / 资产净值走势 / 资金流动 /
// 收益日历 / 清仓复盘 / 浮亏回本 / 持仓结构 / 收益归因 / 货基收益），符合 components.md
// 的 PageToc 接入判据（10 项已超过「>6 就需要目录」的判据）；条目顺序
// 由 DOM 实序决定（usePageNav 扫描 nav-* 锚点），本表只管 id→标签，且与各 SectionHeader
// 标题逐字一致。「浮亏回本」无浮亏时整块不渲染，标签随之隐没（缺锚点即不出现，不需要占位）。
//
// 2026-11-28 起下半页 5 块包了 LazySection（锚点常驻、内容懒挂，见该组件文件头）：
// 锚点仍在 DOM 里 ⇒ 导航项完整、goTo 有落点；`useLazyNav` 在跳转前先把目标块激活，
// 免得跳过去对着一块空白等内容自己长出来。min-height 取家庭档实测高度
// （1440×1000 走查：717 / 399 / 1846 / 2465 / 776），占位偏矮会让下方锚点整体上移。
const pageMain = ref<HTMLElement>();
const NAV_LABELS: Record<string, string> = {
  "nav-overview": "收益概览",
  "nav-money-fund": "货币基金收益",
  "nav-cycles": "清仓复盘",
  "nav-net-worth": "资产净值走势",
  "nav-cash-flow": "资金流动",
  "nav-break-even": "浮亏回本",
  "nav-structure": "持仓结构",
  "nav-excess": "区间表现",
  "nav-calendar": "收益日历",
  "nav-attribution": "收益归因"
};
const nav = usePageNav(pageMain, { labels: NAV_LABELS });
const { items: navItems, activeId: navActiveId } = nav;
/** 跳转要先激活懒加载区块（`LazySection` 未挂载时导航只有占位可落） */
const goToNavSection = useLazyNav(nav);

// #871 / #947：收益概览、货基、净值、清仓均已自含取数；本页只持 ref，
// 「刷新数据」逐个显式联动（避免「本页刷新了、卡片还是旧数」）。
const netWorth = ref<InstanceType<typeof NetWorthTrendSection> | null>(null);
const returnOverview = ref<InstanceType<typeof ReturnOverviewSection> | null>(
  null
);
const moneyFund = ref<InstanceType<typeof MoneyFundIncomeSection> | null>(null);
const breakEven = ref<InstanceType<typeof BreakEvenSection> | null>(null);
const cashFlow = ref<InstanceType<typeof CashFlowPanel> | null>(null);
const excess = ref<InstanceType<typeof ExcessSection> | null>(null);

/** 页头「刷新数据」：真刷新，不摆样子 */
const reloadAll = async () => {
  loading.value = true;
  try {
    await Promise.all([
      netWorth.value?.refresh(),
      returnOverview.value?.refresh(),
      moneyFund.value?.refresh(),
      breakEven.value?.refresh(),
      cashFlow.value?.refresh(),
      excess.value?.refresh()
    ]);
  } finally {
    loading.value = false;
  }
};

/**
 * 首屏骨架的关闭时机 = 账户列表返回。
 *
 * **不能等区块的「加载完成」事件**：骨架与内容在模板里是 `v-if / v-else` 互斥的，
 * 骨架显示期间区块没挂载、永远发不出事件（2026-11-28 走查实测卡在骨架屏的死锁）。
 * 账户列表是父页唯一自发的请求，用它当信号；各区块随后各自取数并自管 loading 态。
 */
onMounted(async () => {
  await loadLedgers();
  initialLoading.value = false;
});

// window resize 监听与 onBeforeUnmount 的三路 dispose 均已移交 composable（#2164）。
// 主题切换（暗色）重绘也由 composable 内置的 `watch(themeTick, render)` 覆盖。
</script>

<style lang="scss" scoped>
/* 内容区与 PageHeaderBar 同宽同内边距（--layout-content-width / --space-standard），
   保证页头与内容左边缘严格对齐；与 dividends / inventory / profile 同值
   （#1501 / #1506）。**页头不在这个容器里**——它是 flex 列，会让 .page-header
   的 `margin: 0 auto` 把「拉伸」顶掉（详见模板里 PageHeaderBar 上方的注释）。 */
.analysis-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-section);
  max-width: var(--layout-content-width);
  padding: 0 var(--space-standard);
  margin: 0 auto;
}

/* 口径切换条：吸附在视口顶部（页头滚走后口径仍在视野里）。它是 shell 的**第一个**
   子元素，gap 不作用于首个子元素上方，`top: 0` 停住时不会有 48px 缝露出内容。
   ⚠️ 底色只能用 `--bg-surface`：内容区底两主题不同源（浅 --bg-warm / 暗 #020409）。 */
.analysis-scope {
  position: sticky;
  top: 0;
  z-index: 10;
  padding-block: var(--space-compact);
  background: var(--bg-surface);
}

.analysis-scope-empty {
  padding: var(--space-section) 0;
  font-size: var(--el-font-size-small);
  color: var(--text-tertiary-ink);
  text-align: center;
}

/* 页内导航两级布局（components.md PageToc）：<xl 单列（胶囊在正文上方）；
   xl+ 主列 + 160px 右目录 rail。列间距先前沿用 --space-5（20px），比 shell 的
   区块纵向间距（48px）小一档，视觉上 rail 像贴在正文右边缘；改 --space-standard
   （24px）与页头 / 内容区的横向内边距同值——「同一层级的留白用同一个令牌」。 */
.analysis-body {
  display: flex;
  gap: var(--space-standard);
}

/* 主列 = 纵向块栈，块间距与 shell 同级（--space-section）。2026-11-27 实测修：此前
   没有 gap，各区块间距 0 / −1px，只剩 SectionHeader 自带的 12px 撑着，七段挤成一片。 */
.analysis-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-section);
  min-width: 0;
}

/* 跨页指路条：与区块同宽、不抢视线；负 margin 抵消 shell 间距，贴在页头下方。 */
.analysis-crosslink {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  align-items: center;
  margin-top: calc(var(--space-section) * -1 + 8px);
  font-size: var(--el-font-size-small);
}
</style>
