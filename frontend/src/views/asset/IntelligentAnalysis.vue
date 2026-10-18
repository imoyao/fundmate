<!--
  复盘（时间维度的表现）—— 原「智能分析」，#2150 重新定义定位

  前身是「AI 驱动的资产健康度诊断」假数据页：匹配度 75%、配置建议比例、
  收益预测曲线、风险预警条目全部是模板硬编码，全仓零入口。
  2026-10 与原 AssetOverview.vue（#1195 已完成真实数据改造但无路由的死文件）合体，
  页面只展示能从账本真实计算的数据。**无数据源的推测性面板（收益预测 /
  AI 配置建议 / 事件预警）一律不上屏**：账本软件只算已发生的账，不编未来的数。

  ── #2150：一句话定位 ──────────────────────────────────────────────
  **只看「时间维度上的表现」，不看资产结构。**

  与同批两页的分工（沿用 `docs/working-notes/page-split-welcome-vs-panorama-2026-08-13.md`
  已确立的「拆解（composition）归资产总览，表现 + 目标归投资概览」口径）：

  | 页面 | 回答的问题 | 形态 |
  |---|---|---|
  | 投资概览（welcome） | 我有多少钱？离目标多远？ | 结论（净值快照 + XIRR + 温度 + 日历） |
  | 资产总览（panorama） | 钱是**怎么铺开**的？结构健不健康？ | 拆解（瀑布图 + 桑基 + 多维视图） |
  | **本页（复盘）** | 我的钱**经历了什么**？表现从哪来？ | **时间序列**（净值走势 + 收益/现金流） |

  ── #2150：删掉了什么，为什么 ──────────────────────────────────────
  本页曾有一整块与 panorama **同字段、同接口、同算法**的内容。panorama 自己
  已为同一形态做过裁决（`panorama/index.vue:66-72` 删 `AssetInsightPanel`：
  「同一份数据在首屏重复第二遍」），**那条裁决同样适用于本页**——这是本卡
  最该被纠正的不一致。已整块删除：

  1. 「家庭资产汇总」总资产 + 环比/同比  ← panorama `OverviewSummaryCard` 首卡；
  2. 大类占比卡片网格（`(d.value/total)*100`）← panorama `CategoryBalanceTable:258` 逐字同公式；
  3. `category_distribution` 环形图 ← panorama 瀑布图 + 明细表（该字段全站**只画一次**）；
  4. 「近期持仓表现」表（`getPositionGroups("type")`）← panorama `DetailGroupList`。

  「风险热力图」空态卡更早已随 #2156 整卡下线。

  ── 保留的独占项（本页存在的理由）──────────────────────────────────
  - **资产净值走势**：welcome 已明确让出（`WelcomeAssetBoard.vue:131-138`
    「净值曲线归复盘页规划」），panorama 只用 snapshots 取最新环比/同比、
    **不画曲线**。全站唯一。

  ── 已迁出 / 待迁出 ──────────────────────────────────────────────
  - 幽灵重复告警（`GhostDuplicateBanner`）本质属**对账**范畴（后端注释自带定性：
    `summary_service.py:1045-1066`），待对账工作台开出「跨账本重复交易」域后迁走
    （#2151）。在域 D 存在之前留在本页，是「异常要看得见」的权宜。
-->
<template>
  <div
    class="analysis-shell min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 幽灵重复告警：属对账范畴（#2151 迁往对账工作台「跨账本重复交易」域）。
         域 D 存在之前留在本页，因为「异常要看得见」优先于「归属洁癖」。 -->
    <GhostDuplicateBanner />

    <PageHeaderBar
      title="复盘"
      subtitle="时间维度上的表现：净值怎么走、收益从哪来"
      :updated-at="updatedAtLabel"
    >
      <template #action>
        <el-button :loading="loading" @click="reloadAll">
          <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新数据
        </el-button>
      </template>
    </PageHeaderBar>

    <!-- 结构拆解不在这里：指一条明路，而不是让用户自己猜「想看结构该去哪」。
         #2150 删掉与资产总览重复的四块后，页面从「堆砌」变成「单一主题」，
         此条链接就是那次删除的可见交代。 -->
    <p
      class="analysis-crosslink"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      本页只看时间维度的表现。想看资产结构（大类占比、产品类型、账户拆解），
      去<el-button text size="small" @click="router.push('/panorama')"
        >资产总览</el-button
      >。
    </p>

    <!-- #2156 铁律 1「结构一致」：删掉风险热力图与 #2150 重复四块后，真实区块
         为「收益概览 / 清仓周期复盘 / 货币基金收益 / 资产净值走势」四段
         （#2131 新增清仓周期复盘区块，含表格，故 table-rows=5 与真实行数匹配）。 -->
    <PageSkeleton
      v-if="initialLoading"
      :cards="3"
      :chart-cols="2"
      :table-rows="5"
    />

    <template v-else>
      <!-- 收益概览（真实 XIRR，无预测） -->
      <section>
        <SectionHeader title="收益概览" :info="xirrScopeInfo">
          <!-- #2153：口径开关与投资概览（首页）逐字同款——同一时刻两页绑定的
               参数一致，数值天然一致；口径说明挂在 info（tooltip），随开关联动 -->
          <template #action>
            <IncludeCashSwitch
              v-model="includeCashEquivalents"
              @change="loadXirr"
            />
          </template>
        </SectionHeader>
        <MetricGrid>
          <!-- value-color：本页主数字统一走品牌文字色 `--brand-ink`
               （WCAG AA：白底 5.86:1）。默认 `--text-primary` 是中性暖黑 #2d2a24，
               作为「这一页的主角数字」缺少品牌识别，看不出是可交互的分析结论区。
               ⚠️ 不要用 `--brand-700`：它作文字仅 3.73:1，不达标。 -->
          <MetricCard
            title="年化收益率 (XIRR)"
            :value="xirrRateLabel"
            unit="%"
            featured
            value-color="var(--brand-ink)"
            :caption="xirrCaption"
          />
          <MetricCard
            title="总收益"
            :value="xirrReturnLabel"
            value-color="var(--brand-ink)"
            caption="含已赎回部分"
          />
          <MetricCard
            title="当前市值"
            :value="xirrCurrentValueLabel"
            value-color="var(--brand-ink)"
            caption="在投本金的当前价值"
          />
          <MetricCard
            title="总投入"
            :value="xirrInvestedLabel"
            value-color="var(--brand-ink)"
            caption="累计投入本金"
          />
        </MetricGrid>
      </section>

      <!-- 货币基金收益（#947：万份收益口径，独立于 XIRR） -->
      <section v-if="moneyFundIncome">
        <SectionHeader
          title="货币基金收益"
          info="按「万份收益 × 持有份额」估算，与上方 XIRR 口径不同（XIRR 衡量交易现金流的时间价值），两者不可相加；本项已计入总资产"
        />
        <MetricGrid>
          <MetricCard
            title="今日收益"
            :value="mfTodayLabel"
            value-color="var(--brand-ink)"
            :caption="mfTodayCaption"
            featured
          />
          <MetricCard
            title="累计收益"
            :value="mfTotalLabel"
            value-color="var(--brand-ink)"
            caption="持有期累计（万份收益 × 份额）"
          />
        </MetricGrid>
      </section>

      <!-- 清仓周期复盘（#2131：已落袋表现的时间维度——与本页「表现从哪来」同主题）。
           自加载自降级：接口失败渲染空态表格，不影响上方 XIRR 与下方净值走势。 -->
      <ClearedCyclesSection />

      <!-- 资产净值走势：本页的**独占项**（welcome 让出、panorama 只取快照做环比同比）。
           原先与「资产分布」环形图并排成两列，环形图删掉后满宽 —— 时间序列本来就
           该宽（横轴是日期），挤在半屏里读不出趋势。 -->
      <section>
        <SectionHeader
          title="资产净值走势"
          info="来自每日资产快照记录，未打卡则无曲线"
        />
        <CardBlock>
          <div class="relative h-72">
            <canvas ref="profitTrendChartRef" />
            <p
              v-if="!profitTrendData.length"
              class="absolute inset-0 flex items-center justify-center text-sm"
              :style="{ color: 'var(--text-tertiary-ink)' }"
            >
              暂无资产快照数据
            </p>
          </div>
        </CardBlock>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import echarts from "@/plugins/echarts";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import GhostDuplicateBanner from "@/components/GhostDuplicateBanner/index.vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import IncludeCashSwitch from "@/components/IncludeCashSwitch/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import ClearedCyclesSection from "@/views/asset/cleared-cycles/ClearedCyclesSection.vue";
import { getSnapshots, type AssetSnapshotItem } from "@/api/summary";
import {
  getMoneyFundIncome,
  getPortfolioXirr,
  type MoneyFundIncomeData,
  type XirrData
} from "@/api/performance";
import { getCssVar, getCssVarWithAlpha } from "@/composables/echarts/theme";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import { formatAmount } from "@/utils/currency";

defineOptions({ name: "AssetAnalysis" });

const router = useRouter();

const profitTrendChartRef = ref<HTMLElement | null>(null);

// 真实数据源：#2150 删掉 distribution / positions 两条链路后，本页只读两处 ——
// 净值走势 /summary/snapshots/、收益 /performance/xirr/（+ 货基 /performance/money-fund-income/）。
const profitTrendData = ref<Array<{ date: string; net: number }>>([]);
const latestSnapshot = ref<AssetSnapshotItem | null>(null);
const xirr = ref<XirrData | null>(null);
// #2153：XIRR「是否含现金等价物」口径——与投资概览（welcome）同语义、同默认值
// （false=剔除现金，与后端 include_cash_equivalents 默认值一致）。两页各自持本地
// 状态（issue 方案 1「切换后本地生效」），但开关与口径文案逐字一致，任一处可见、语义相同。
const includeCashEquivalents = ref(false);
const moneyFundIncome = ref<MoneyFundIncomeData | null>(null);

const initialLoading = ref(true);
const loading = ref(false);

const updatedAtLabel = computed(() =>
  latestSnapshot.value ? `${latestSnapshot.value.snapshot_date} 更新` : ""
);

// ── XIRR（真实收益；cashflow_count=0 视为无数据，不显示假 0%） ──
const xirrRateLabel = computed(() => {
  const d = xirr.value;
  return d && d.cashflow_count > 0 ? (d.xirr * 100).toFixed(2) : null;
});
const xirrReturnLabel = computed(() => {
  const d = xirr.value;
  return d && d.cashflow_count > 0 ? formatSignedYuan(d.total_return) : null;
});
const xirrCurrentValueLabel = computed(() => {
  const d = xirr.value;
  return d && d.cashflow_count > 0 ? formatYuan(d.current_value) : null;
});
const xirrInvestedLabel = computed(() => {
  const d = xirr.value;
  return d && d.cashflow_count > 0 ? formatYuan(d.total_invested) : null;
});
const xirrCaption = computed(() => {
  const d = xirr.value;
  return d && d.cashflow_count > 0
    ? `基于 ${d.cashflow_count} 笔交易现金流`
    : "录入交易流水后自动计算";
});

/** #2153：收益概览口径说明——沿用首段说明 + 当前口径，后半句与首页
 *  WelcomeXirrTemperature 的口径小字逐字一致（验收「语义一致」） */
const xirrScopeInfo = computed(() =>
  includeCashEquivalents.value
    ? "XIRR 由已录入的交易现金流真实计算，录入交易后自动生成；本页不做收益预测。当前口径：含货币基金/逆回购/现金，反映账户总收益"
    : "XIRR 由已录入的交易现金流真实计算，录入交易后自动生成；本页不做收益预测。当前口径：基于主动投资交易，不含货币基金等现金等价物"
);

const formatYuan = (n: number, p = 0) => `¥${formatAmount(n || 0, p)}`;
const formatSignedYuan = (n: number) =>
  `${n >= 0 ? "+" : "-"}${formatYuan(Math.abs(n || 0))}`;

// ── 货币基金收益（#947）────────────────────────────
// 口径：万份收益 nav_per_10k × 持有份额，整数分算完后转元，由后端算好；
// 前端只做展示，**不做二次运算**（正负号也用后端给的 today_income 语义）。
// 无货基时接口返回 null → 不渲染该 section，而不是显示「¥0」误导成「没赚到钱」。
const mfTodayLabel = computed(() => {
  const d = moneyFundIncome.value;
  return d ? formatSignedYuan(d.today_income) : null;
});
const mfTotalLabel = computed(() => {
  const d = moneyFundIncome.value;
  return d ? formatSignedYuan(d.total_income) : null;
});
const mfTodayCaption = computed(() => {
  const d = moneyFundIncome.value;
  if (!d) return "";
  const days = d.daily_series?.length ?? 0;
  return days > 0 ? `近${days}天有收益记录` : "暂无收益记录";
});

const paintProfitTrendChart = (chart: echarts.ECharts) => {
  chart.setOption({
    tooltip: { trigger: "axis" },
    grid: { right: "4%", bottom: "8%", containLabel: true, left: "4%" },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: profitTrendData.value.map(d => d.date),
      axisLabel: { fontSize: 10 }
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 10, formatter: "¥{value}" }
    },
    series: [
      {
        name: "净资产",
        type: "line",
        smooth: true,
        data: profitTrendData.value.map(d => d.net),
        // 面积渐变按折线主色 --brand-700 派生透明度（#2156：原硬编码
        // rgba(255,107,0,…) 与 --brand-700(#e34f38) 不是同色，暗色更明显）。
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            {
              offset: 0,
              color: getCssVarWithAlpha("--brand-700", 0.3, "#e34f38")
            },
            {
              offset: 1,
              color: getCssVarWithAlpha("--brand-700", 0.05, "#e34f38")
            }
          ])
        },
        // 主色走语义变量（--brand-700），避免硬编码 hex（design.md 红线）
        itemStyle: { color: getCssVar("--brand-700", "#e34f38") },
        lineStyle: { width: 2 },
        symbol: "circle",
        symbolSize: 4
      }
    ]
  });
};

// #2164：图表实例生命周期（init / window resize / 卸载 dispose / 主题重绘 /
// keepAlive 恢复时 resize）统一交给 useEchartsLifecycle；本文件只负责「往给定实例
// setOption」。`reuse: true` 保留原先 `chart ?? echarts.init()` 的复用语义——
// 否则每次刷新都重建实例，动画状态丢失且肉眼可见地闪一下。
// #2156 / #2150：风险热力图整卡下线、「资产分布」环形图随 #2150 删除后，
// 本文件只剩「资产净值走势」一张 ECharts 图，故下方 specs 只登记这一处。
const { render: initCharts } = useEchartsLifecycle(
  [
    {
      ref: profitTrendChartRef,
      build: el => {
        const chart = echarts.init(el);
        paintProfitTrendChart(chart);
        return chart;
      },
      update: paintProfitTrendChart
    }
  ],
  { keepAlive: true, reuse: true, autoRenderOnMount: false }
);

const loadProfitTrend = async () => {
  try {
    const res = await getSnapshots();
    const list = res?.data ?? [];
    profitTrendData.value = list.map(i => ({
      date: i.snapshot_date,
      net: i.net_worth
    }));
    latestSnapshot.value = list.length ? list[list.length - 1] : null;
  } catch {
    profitTrendData.value = [];
    latestSnapshot.value = null;
  }
};

// #2153：请求序号——快速切换口径时丢弃过期响应，防止旧口径数据覆盖新口径
// （否则会出现「开关显示剔除现金、数字却是含现金」的显示与开关失步）。
let xirrReqSeq = 0;
const loadXirr = async () => {
  const seq = ++xirrReqSeq;
  try {
    const res = await getPortfolioXirr(
      "portfolio",
      undefined,
      includeCashEquivalents.value
    );
    if (seq !== xirrReqSeq) return;
    xirr.value = res?.data ?? null;
  } catch {
    if (seq === xirrReqSeq) xirr.value = null;
  }
};

/** 货币基金收益（#947）：接口异常时置 null，页面隐藏该区块而不是显示 0 */
const loadMoneyFundIncome = async () => {
  try {
    const res = await getMoneyFundIncome({ scope: "family" });
    moneyFundIncome.value = res?.data ?? null;
  } catch {
    moneyFundIncome.value = null;
  }
};

const loadAll = () =>
  Promise.all([loadProfitTrend(), loadXirr(), loadMoneyFundIncome()]);

/** 页头「刷新数据」：真刷新，不摆样子 */
const reloadAll = async () => {
  loading.value = true;
  try {
    await loadAll();
    await nextTick();
    initCharts();
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  await loadAll();
  initialLoading.value = false;
  await nextTick();
  initCharts();
});

// window resize 监听与 onBeforeUnmount 的三路 dispose 均已移交 composable（#2164）。
// 主题切换（暗色）重绘也由 composable 内置的 `watch(themeTick, render)` 覆盖。
</script>

<style scoped>
.analysis-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-section);
  max-width: var(--layout-content-width);
  padding: 0 var(--space-standard);
  margin: 0 auto;
}

/* 跨页指路条：与区块同宽、不抢视线，靠 el-button text 承接跳转。
   负 margin 抵消 shell 的 section 间距，让它贴在页头下方而不是自成一段。 */
.analysis-crosslink {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  align-items: center;
  margin-top: calc(var(--space-section) * -1 + 8px);
  font-size: var(--el-font-size-small);
}
</style>
