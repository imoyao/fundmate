<!--
  智能分析（真实数据版，#1798）

  前身是「AI 驱动的资产健康度诊断」假数据页：匹配度 75%、配置建议比例、
  收益预测曲线、风险预警条目全部是模板硬编码，全仓零入口。

  2026-10 与原 AssetOverview.vue（#1195 已完成真实数据改造但无路由的死文件）合体：
  页面只展示能从账本真实计算的数据 —— 分布走 /api/summary/distributions/、
  净值走势走 /api/summary/snapshots/、持仓走 /api/summary/groups、
  收益走 /api/performance/xirr/。**无数据源的推测性面板（收益预测 / AI 配置建议 /
  事件预警）一律不上屏**：账本软件只算已发生的账，不编未来的数。
-->
<template>
  <div
    class="intelligent-analysis min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <GhostDuplicateBanner />

    <PageHeaderBar
      title="智能分析"
      subtitle="基于真实记账数据的资产结构与收益分析"
      :updated-at="updatedAtLabel"
    >
      <template #action>
        <el-button :loading="loading" @click="reloadAll">
          <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新数据
        </el-button>
      </template>
    </PageHeaderBar>

    <div class="analysis-shell">
      <PageSkeleton
        v-if="initialLoading"
        :cards="4"
        :chart-cols="3"
        :table-rows="5"
      />

      <template v-else>
        <!-- 收益概览（真实 XIRR，无预测） -->
        <section>
          <SectionHeader
            title="收益概览"
            info="XIRR 由已录入的交易现金流真实计算，录入交易后自动生成；本页不做收益预测"
          />
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

        <!-- 家庭资产汇总（/summary/distributions/ + /summary/snapshots/） -->
        <section>
          <SectionHeader
            title="家庭资产汇总"
            info="总资产与大类占比来自资产分布聚合，环比/同比来自最近一条资产快照"
          />
          <CardBlock>
            <div
              class="flex flex-col md:flex-row md:items-start justify-between gap-6"
            >
              <div>
                <p class="text-sm" :style="{ color: 'var(--text-secondary)' }">
                  总资产
                </p>
                <p
                  class="text-4xl font-bold mt-1"
                  :style="{ color: 'var(--brand-ink)' }"
                >
                  {{ formatYuan(totalAssets) }}
                </p>
                <div class="flex flex-wrap items-center gap-x-6 gap-y-2 mt-2">
                  <p
                    v-if="monthlyChangePct !== null"
                    class="flex items-center gap-2"
                  >
                    <RiseFallText
                      :value="monthlyChangePct"
                      suffix="%"
                      :precision="1"
                      size="lg"
                    />
                    <span
                      class="text-sm"
                      :style="{ color: 'var(--text-tertiary-ink)' }"
                      >较上月</span
                    >
                  </p>
                  <p
                    v-if="yearlyChangePct !== null"
                    class="flex items-center gap-2"
                  >
                    <RiseFallText
                      :value="yearlyChangePct"
                      suffix="%"
                      :precision="1"
                      size="lg"
                    />
                    <span
                      class="text-sm"
                      :style="{ color: 'var(--text-tertiary-ink)' }"
                      >较去年同期</span
                    >
                  </p>
                  <p
                    v-if="monthlyChangePct === null && yearlyChangePct === null"
                    class="text-sm"
                    :style="{ color: 'var(--text-tertiary-ink)' }"
                  >
                    暂无环比数据（每日打卡资产快照后生成）
                  </p>
                </div>
              </div>

              <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div
                  v-for="card in categoryCards"
                  :key="card.name"
                  class="rounded-lg p-4 border"
                  :style="{
                    background: 'var(--bg-soft)',
                    borderColor: 'var(--border-light)'
                  }"
                >
                  <p
                    class="text-xs font-medium"
                    :style="{ color: 'var(--text-secondary)' }"
                  >
                    {{ card.name }}
                  </p>
                  <p
                    class="text-lg font-bold mt-1"
                    :style="{ color: 'var(--brand-ink)' }"
                  >
                    {{ formatYuan(card.value) }}
                  </p>
                  <div class="mt-2">
                    <div
                      class="flex justify-between text-[10px] mb-1"
                      :style="{ color: 'var(--text-tertiary-ink)' }"
                    >
                      <span>占比 {{ card.share.toFixed(1) }}%</span>
                    </div>
                    <div
                      class="h-1.5 rounded-full overflow-hidden"
                      :style="{ background: 'var(--border-light)' }"
                    >
                      <div
                        class="h-full rounded-full"
                        :style="{
                          background: 'var(--brand-700)',
                          width: card.share + '%'
                        }"
                      />
                    </div>
                  </div>
                </div>
                <p
                  v-if="!categoryCards.length"
                  class="col-span-4 text-center text-sm py-8"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                >
                  暂无分类资产数据
                </p>
              </div>
            </div>
          </CardBlock>
        </section>

        <!-- 图表区：三张真实图（分布 / 快照走势 / 风险评分空态） -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <CardBlock>
            <SectionHeader
              title="资产分布"
              info="各大类市值占比（含汇率换算）"
            />
            <!-- 资产分布（#2164：收编到统一组件 AssetAllocationDonut，替代原先手写的
                 pie option；分类 3~6 类，命中 components.md「≤6 类用环形」判据） -->
            <div class="h-52">
              <AssetAllocationDonut
                :data="donutData"
                :legend-font-size="11"
                empty-text="暂无数据"
              />
            </div>
          </CardBlock>

          <CardBlock>
            <SectionHeader
              title="资产净值走势"
              info="来自每日资产快照记录，未打卡则无曲线"
            />
            <div class="relative h-52">
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

          <CardBlock>
            <SectionHeader
              title="风险热力图"
              info="风险评分数据源尚未接入，仅展示空态（#1195 下线假数据）"
            />
            <div class="h-52">
              <canvas ref="riskHeatmapChartRef" />
            </div>
            <div
              class="mt-3 flex justify-center space-x-4 text-[10px]"
              :style="{ color: 'var(--text-tertiary-ink)' }"
            >
              <span class="flex items-center"
                ><span class="w-2 h-2 bg-green-500 rounded mr-1" />低风险</span
              >
              <span class="flex items-center"
                ><span class="w-2 h-2 bg-amber-500 rounded mr-1" />中风险</span
              >
              <span class="flex items-center"
                ><span class="w-2 h-2 bg-red-500 rounded mr-1" />高风险</span
              >
            </div>
          </CardBlock>
        </div>

        <!-- 近期持仓表现（真实分组数据） -->
        <section>
          <SectionHeader title="近期持仓表现">
            <template #action>
              <el-button
                text
                size="small"
                @click="router.push('/asset/ledgers')"
              >
                查看全部持仓
                <IconifyIconOffline icon="ep:right" class="ml-1" />
              </el-button>
            </template>
          </SectionHeader>
          <CardBlock>
            <div class="overflow-x-auto">
              <table class="min-w-full text-sm">
                <thead>
                  <tr
                    class="border-b text-left"
                    :style="{
                      color: 'var(--text-tertiary-ink)',
                      borderColor: 'var(--border-light)'
                    }"
                  >
                    <th class="px-4 py-3 font-normal">资产名称</th>
                    <th class="px-4 py-3 font-normal">持仓市值</th>
                    <th class="px-4 py-3 font-normal">盈亏(元)</th>
                    <th class="px-4 py-3 font-normal">盈亏比例</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="item in recentHoldings"
                    :key="item.id"
                    class="border-b"
                    :style="{
                      borderColor: 'var(--border-light)',
                      color: 'var(--text-primary)'
                    }"
                  >
                    <td class="px-4 py-3 font-medium">
                      {{ item.name
                      }}<span
                        v-if="item.symbol"
                        class="ml-1"
                        :style="{ color: 'var(--text-tertiary-ink)' }"
                        >({{ item.symbol }})</span
                      >
                    </td>
                    <!-- 持仓市值染品牌文字色，与页面其它主数字一致；
                         盈亏两列保持 RiseFallText 涨跌色（不染品牌色，见 design.md
                         「指标数值不染涨跌色」的反面：涨跌值**必须**染涨跌色）。 -->
                    <td
                      class="px-4 py-3"
                      :style="{ color: 'var(--brand-ink)' }"
                    >
                      {{ formatYuan(item.market_value) }}
                    </td>
                    <td class="px-4 py-3">
                      <RiseFallText
                        :value="item.pnl"
                        suffix=""
                        :precision="0"
                      />
                    </td>
                    <td class="px-4 py-3">
                      <RiseFallText :value="pnlPct(item)" />
                    </td>
                  </tr>
                  <tr v-if="!recentHoldings.length">
                    <td
                      colspan="4"
                      class="px-4 py-8 text-center text-sm"
                      :style="{ color: 'var(--text-tertiary-ink)' }"
                    >
                      暂无持仓数据
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </CardBlock>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import echarts from "@/plugins/echarts";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import GhostDuplicateBanner from "@/components/GhostDuplicateBanner/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import {
  getDistributions,
  getSnapshots,
  getPositionGroups,
  type DistributionsData,
  type AssetSnapshotItem,
  type GroupItem
} from "@/api/summary";
import {
  getMoneyFundIncome,
  getPortfolioXirr,
  type MoneyFundIncomeData,
  type XirrData
} from "@/api/performance";
import { getCssVar } from "@/composables/echarts/theme";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import { formatAmount } from "@/utils/currency";

defineOptions({ name: "AssetAnalysis" });

const router = useRouter();

const profitTrendChartRef = ref<HTMLElement | null>(null);
const riskHeatmapChartRef = ref<HTMLElement | null>(null);

/** 资产分布喂给统一组件 AssetAllocationDonut 的数据（#2164） */
const donutData = computed(() =>
  distributionData.value.map(d => ({ name: d.name, value: d.value }))
);

// 真实数据源（#1195 基线，#1798 合体）：分布 /summary/distributions/、
// 净值走势 /summary/snapshots/、持仓 /summary/groups、收益 /performance/xirr/。
const distributionData = ref<Array<{ name: string; value: number }>>([]);
const profitTrendData = ref<Array<{ date: string; net: number }>>([]);
const distributions = ref<DistributionsData | null>(null);
const latestSnapshot = ref<AssetSnapshotItem | null>(null);
const positionItems = ref<GroupItem[]>([]);
const xirr = ref<XirrData | null>(null);
const moneyFundIncome = ref<MoneyFundIncomeData | null>(null);

const initialLoading = ref(true);
const loading = ref(false);

const totalAssets = computed(() => distributions.value?.total_assets ?? 0);
const monthlyChangePct = computed(
  () => latestSnapshot.value?.monthly_change_pct ?? null
);
const yearlyChangePct = computed(
  () => latestSnapshot.value?.yearly_change_pct ?? null
);
const updatedAtLabel = computed(() =>
  latestSnapshot.value ? `${latestSnapshot.value.snapshot_date} 更新` : ""
);

const categoryCards = computed(() => {
  const dist = distributions.value;
  if (!dist) return [];
  const total = dist.total_assets || 0;
  return (dist.category_distribution || []).map(d => ({
    name: d.name,
    value: d.value,
    share: total ? (d.value / total) * 100 : 0
  }));
});

const recentHoldings = computed(() =>
  [...positionItems.value]
    .sort((a, b) => b.market_value - a.market_value)
    .slice(0, 8)
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
const pnlPct = (item: GroupItem) => {
  const cost = item.market_value - item.pnl;
  return cost ? (item.pnl / cost) * 100 : 0;
};

// #2164：原先给「资产分布」手写 pie 用的调色板已随收编删除 —— donut 内部缺失
// colorMap 时自行回退 --chart-01~08 循环，与本文件原来的行为一致。

// #2164：资产分布原先也是本文件手写的一整套 pie option（tooltip / legend / series /
// 空态兜底），已收编到统一组件 `AssetAllocationDonut`（components.md 明文「强制复用」，
// 且 `scripts/guard_no_duplicate_pie.py` 在 CI 拦新增）。
//
// 顺带修掉三处口径不一致（都是 donut 已覆盖的更优行为）：
//   1. 图例补占比 —— 原 echarts legend 只显分类名，违反「图例即清单（分类名 + 占比）」；
//   2. tooltip 统一 `¥…（x.x%）` —— 原用 echarts 默认 `{b}: {c} ({d}%)`，无货币符号；
//   3. 空态判定补 `total === 0` 防护 —— 原先只判 `length === 0`，而 echarts 在总和为 0
//      时会按分类数均分扇区（误导），donut 内部已处理。
// 本文件不再直接持有该图表的实例：它由 donut 自带的 useEchartsLifecycle 管理
// （含 keepAlive 恢复 resize），故不在下方 specs 里登记。
//
// 注意：同页上部 `categoryCards` 已用「品牌色条 + share%」画过一遍大类分布，
// 与本图是重复呈现。收编时一并评估过去重（见 #2164 备注），本卡不改动 card 布局。

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
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(255, 107, 0, 0.3)" },
            { offset: 1, color: "rgba(255, 107, 0, 0.05)" }
          ])
        },
        // 主色走语义变量（--brand-700），避免硬编码 hex（design.md 红线）
        itemStyle: { color: getCssVar("--brand-700", "#FF6B00") },
        lineStyle: { width: 2 },
        symbol: "circle",
        symbolSize: 4
      }
    ]
  });
};

// 风险热力图：当前无真实风险评分数据源，仅展示空态提示（#1195 决策沿用）
const paintRiskHeatmapChart = (chart: echarts.ECharts) => {
  chart.setOption({
    title: {
      text: "暂无风险评分数据",
      left: "center",
      top: "center",
      textStyle: {
        color: getCssVar("--text-tertiary", "#999"),
        fontSize: 12,
        fontWeight: "normal"
      }
    }
  });
};

// #2164：三个图表的实例生命周期（init / window resize / 卸载 dispose / 主题重绘 /
// keepAlive 恢复时 resize）统一交给 useEchartsLifecycle；本文件只负责「往给定实例
// setOption」。`reuse: true` 保留原先 `chart ?? echarts.init()` 的复用语义——
// 否则每次刷新都重建实例，动画状态丢失且肉眼可见地闪一下。
// 主题切换重绘由 composable 内置的 `watch(themeTick, render)` 覆盖（下方不再重复写）。
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
    },
    {
      ref: riskHeatmapChartRef,
      build: el => {
        const chart = echarts.init(el);
        paintRiskHeatmapChart(chart);
        return chart;
      },
      update: paintRiskHeatmapChart
    }
  ],
  { keepAlive: true, reuse: true, autoRenderOnMount: false }
);

const loadDistribution = async () => {
  try {
    const res = await getDistributions();
    const dist = res?.data ?? null;
    distributions.value = dist;
    distributionData.value = dist?.category_distribution ?? [];
  } catch {
    distributions.value = null;
    distributionData.value = [];
  }
};

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

const loadPositions = async () => {
  try {
    const res = await getPositionGroups("type");
    const groups = res?.data ?? [];
    const items: GroupItem[] = [];
    for (const g of groups) {
      if (Array.isArray(g.items)) items.push(...g.items);
    }
    positionItems.value = items;
  } catch {
    positionItems.value = [];
  }
};

const loadXirr = async () => {
  try {
    const res = await getPortfolioXirr("portfolio");
    xirr.value = res?.data ?? null;
  } catch {
    xirr.value = null;
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
  Promise.all([
    loadDistribution(),
    loadProfitTrend(),
    loadPositions(),
    loadXirr(),
    loadMoneyFundIncome()
  ]);

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
</style>
