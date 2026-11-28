<!--
  持仓分析聚合页（#2595 · 全家庭 / 单账户 / 组合三级口径）

  定位：把**已实现**的分析端点聚到一个统一入口，三级口径一处切换——
  不重建任何计算（后端 8 个既有端点直连，前端只做取数与编排）。

  ── 与既有页面的分工（沿用全站「同一份数据只画一次」裁决）──────────────
  | 页面           | 回答的问题                   | 本页关系                     |
  | 复盘 /analysis | 时间维度的表现（净值/日历/清仓） | 日历在此仅作口径上下文复用     |
  | 组合详情       | 单组合的结构与表现             | 组合档与它**同源同口径**（同一批面板/端点）|
  | 账户详情       | 单账户的持仓与收益             | 账户档与它**同源同口径**（同一批面板/端点）|
  | 资产总览       | 钱怎么铺开（结构拆解）         | 不重复（穿透≠结构拆解，口径不同）|

  ⚠️ 「同源同口径」≠「子集视图」（#2739 更正，原措辞「组合档 = 详情页核心块的
  聚合视图」「账户档同理」会被读成子集关系）：本页与详情页是**两个并列入口**——
  本页可切换口径（家庭 / 单账户 / 组合），详情页是固定口径的深读入口。
  同一个账户在两处都能看结构与穿透，数据同源、结论一致，不构成功能冗余；
  本页**不提供**跳转到详情页的深链（#2739 裁定：不给聚合页加深链）。

  账户详情页自 #2739 起也带持仓结构 / 持仓穿透两块（原先那里是一块写着
  「规划中」的占位卡），组件与端点与本页完全同源。

  组件复用（零新计算）：
  - PnlAttribution：本来就支持 ledgerId / portfolioId props（#2135）；
  - PenetrationPanel：#2595 已三级口径化（原组合详情页漏传 scope 的口径错位一并修复）；
  - PnlCalendar：账户维度天然支持（设计文档 §3），组合级后端无此口径 → 组合档隐藏；
  - 超额四卡：getBenchmarkExcess + utils/benchmarkExcess 派生（#2595 上移的唯一出口）。
-->
<template>
  <div
    class="position-analysis p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <PageHeaderBar
      title="持仓分析"
      subtitle="全家庭 / 单账户 / 组合三级口径：表现、超额与穿透，一处看全"
    />

    <!-- 口径切换器（#3287 收敛到 ScopeBar + useAnalysisScope）：
         档位与对象的选择、脏 id 清理、URL 同步都在 composable 里；本页**只 watch**
         口径变化后重取，不接 `change` 事件——两者都接会对同一操作发两次请求。 -->
    <CardBlock class="mb-6">
      <ScopeBar
        :id="id"
        :kind="kind"
        :kinds="SCOPE_KINDS"
        :ledgers="ledgers"
        :portfolios="portfolios"
        :loading="optionsLoading"
        :hint="scopeHint"
        @update:kind="setKind"
        @update:id="setId"
      />
    </CardBlock>

    <!-- 区间表现 vs 基准（#2134）：四卡口径全部来自后端，前端不二次计算 -->
    <MetricGrid class="mb-6">
      <MetricCard
        title="区间收益"
        :value="rangeRateText"
        unit="%"
        :caption="`${RANGE_LABEL} · ${excess?.start_date ?? ''} ~ ${excess?.end_date ?? ''}`"
        :value-color="rangeRateColor"
        featured
      />
      <MetricCard
        title="区间盈亏"
        :value="rangePnlValue"
        :caption="RANGE_LABEL"
      />
      <MetricCard
        title="基准同期"
        :value="benchmarkValue"
        unit="%"
        :caption="benchmarkCaption"
      />
      <MetricCard
        title="超额收益"
        :value="excessValue"
        unit="%"
        :caption="excessCaption"
        :value-color="excessColor"
      />
    </MetricGrid>

    <!-- 收益日历：后端仅支持家庭 / 账户级（设计文档 §3），组合档隐藏不造假口径 -->
    <div v-if="kind !== 'portfolio'" class="mb-6">
      <PnlCalendar :ledger-id="scopeProps.ledgerId" />
    </div>
    <SoftBanner v-else class="mb-6" variant="info" icon="ep:info-filled">
      收益日历暂不支持组合口径——日/月/年三视图见「复盘」页家庭与账户档。
    </SoftBanner>

    <!-- #2135 区间收益归因（原生支持三级口径） -->
    <div class="mb-6">
      <PnlAttribution v-bind="scopeProps" />
    </div>

    <!-- #2617 持仓结构（资产类别 / 股基分列 Top N / 集中度） -->
    <div class="mb-6">
      <PositionStructurePanel v-bind="scopeProps" />
    </div>

    <!-- #870 持仓穿透（#2595 三级口径化；#2617 两档视图，2026-10-30 更名
         「持仓结构 / 穿透持仓」并让持仓结构改环形图） -->
    <PenetrationPanel v-bind="scopeProps" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import ScopeBar from "@/components/ScopeBar/index.vue";
import PnlCalendar from "@/components/PnlCalendar/index.vue";
import PnlAttribution from "@/components/PnlAttribution/index.vue";
import PositionStructurePanel from "@/components/PositionStructurePanel/index.vue";
import PenetrationPanel from "@/components/PenetrationPanel/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import { useAnalysisScope } from "@/composables/analysisScope";
import type { ScopeKind } from "@/composables/analysisScope/toScopeProps";
import { getLedgers, type LedgerItem } from "@/api/ledger";
import { getPortfolios } from "@/api/portfolio";
import { getBenchmarkExcess, type BenchmarkExcessResult } from "@/api/summary";
import {
  benchmarkCaptionOf,
  excessCaptionOf,
  excessColorOf,
  excessValueText,
  excessDateRange,
  EXCESS_RANGE_DAYS
} from "@/utils/benchmarkExcess";
import { formatAmount } from "@/utils/currency";

defineOptions({ name: "PositionAnalysis" });

/** 超额/区间展示口径与组合详情页保持一致（同一 util 出口） */
const RANGE_LABEL = `近 ${EXCESS_RANGE_DAYS} 天`;

/** 本页三档全开：组合档只差收益日历（其余四块同源同口径，见下方 SoftBanner） */
const SCOPE_KINDS: readonly ScopeKind[] = ["family", "ledger", "portfolio"];

/**
 * 口径状态与「面板 props」翻译的唯一出口（`composables/analysisScope`）。
 *
 * 不再在本页写 `toScopeProps(scopeKind, scopeId)`：四个面板共用同一个计算结果，
 * 漏传只能漏在 composable 里（有单测钉住）。#2595 的事故形态就是「组合详情页复用
 * 面板时漏传 scope，安静显示家庭级数据」。
 */
const { kind, id, epoch, isReady, scopeProps, scopeQuery, setKind, setId } =
  useAnalysisScope({ kinds: SCOPE_KINDS });

const ledgers = ref<LedgerItem[]>([]);
const portfolios = ref<{ id: number; name: string }[]>([]);
const optionsLoading = ref(false);

/**
 * 右侧「当前口径」提示。它回答的是**为什么下面没有数**：
 * 切到账户档但还没选账户时，四张卡是 `—`，如果没有这句话，用户会以为是接口挂了。
 * 选中对象后不再重复账户名——下拉里已经写着。
 */
const scopeHint = computed(() => {
  if (kind.value === "family") {
    return ledgers.value.length ? `${ledgers.value.length} 个账户合计` : "";
  }
  if (id.value != null) return "";
  return kind.value === "ledger" ? "选择账户后取数" : "选择组合后取数";
});

// ── #2134 区间表现 vs 基准（family / ledger / portfolio 三级全支持）─────────
const excess = ref<BenchmarkExcessResult | null>(null);

async function excessReload() {
  const q = scopeQuery.value;
  const params: {
    start_date: string;
    end_date: string;
    ledger_id?: number;
    portfolio_id?: number;
  } = { ...excessDateRange() };
  if (q.ledger_id != null) params.ledger_id = q.ledger_id;
  if (q.portfolio_id != null) params.portfolio_id = q.portfolio_id;
  // 纪元快照：快速连续切档时，先发的请求可能后到。不比对就会用旧口径的响应
  // 覆盖新口径的界面——数字与档位标签对不上，而两者看上去都「正常」。
  const mark = epoch.value;
  try {
    const res = await getBenchmarkExcess(params);
    if (mark !== epoch.value) return;
    excess.value = res.data;
  } catch {
    if (mark !== epoch.value) return;
    // 诚实降级：整组「--」，不打断页面主体（与组合详情页同款约定）
    excess.value = null;
  }
}

/**
 * 口径变化 → 重取。
 *
 * `isReady === false`（切到账户/组合档但未选对象）时**必须清空而不是取数**：
 * 不传 id 的请求会拿到家庭级数据，界面却写着「单账户」——静默错口径。
 * 原实现在切档那一刻就 `excessReload()` 了一次，正好命中这个坑（四张卡瞬间
 * 显示家庭数、档位已是「单账户」、选择框还空着）。
 */
watch([kind, id], () => {
  if (!isReady.value) {
    excess.value = null;
    return;
  }
  void excessReload();
});

const rangeRateText = computed(() =>
  excess.value?.range_rate == null ? null : excess.value.range_rate.toFixed(2)
);
const rangeRateColor = computed(() => {
  const v = excess.value?.range_rate;
  if (v == null || v === 0) return "";
  return v > 0 ? "var(--color-rise)" : "var(--color-fall)";
});
const rangePnlValue = computed(() =>
  excess.value?.range_pnl == null ? null : formatAmount(excess.value.range_pnl)
);
const benchmarkValue = computed(() =>
  excess.value?.benchmark?.range_return == null
    ? null
    : excess.value.benchmark.range_return.toFixed(2)
);
const benchmarkCaption = computed(() =>
  benchmarkCaptionOf(excess.value, RANGE_LABEL)
);
const excessValue = computed(() => excessValueText(excess.value));
const excessCaption = computed(() =>
  excessCaptionOf(excess.value, RANGE_LABEL)
);
const excessColor = computed(() => excessColorOf(excess.value));

// ── 切换器数据源 ─────────────────────────────────────────────────────────
async function loadScopeOptions() {
  optionsLoading.value = true;
  try {
    const [ledgerRes, portfolioRes] = await Promise.allSettled([
      getLedgers(),
      getPortfolios()
    ]);
    ledgers.value =
      ledgerRes.status === "fulfilled" ? (ledgerRes.value.data ?? []) : [];
    portfolios.value =
      portfolioRes.status === "fulfilled"
        ? (portfolioRes.value.data ?? [])
        : [];
  } finally {
    optionsLoading.value = false;
  }
}

onMounted(() => {
  void loadScopeOptions();
  // 必须先判 `isReady`：深链只带 `?scope=ledger` 不带 `scope_id` 时（或用户清空了选择），
  // 此时取数会不带 id ⇒ 拿回家庭级数据，而界面标着「单账户」。
  if (isReady.value) void excessReload();
});
</script>

<style scoped lang="scss">
.position-analysis {
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}
</style>
