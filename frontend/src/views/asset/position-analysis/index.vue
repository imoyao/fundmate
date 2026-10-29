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

    <!-- 口径切换器：档位（家庭/账户/组合）+ 具体对象 -->
    <CardBlock class="mb-6">
      <div class="scope-bar">
        <el-radio-group v-model="scopeKind" size="default">
          <el-radio-button value="family">全家庭</el-radio-button>
          <el-radio-button value="ledger">单账户</el-radio-button>
          <el-radio-button value="portfolio">组合</el-radio-button>
        </el-radio-group>
        <el-select
          v-if="scopeKind !== 'family'"
          v-model="scopeId"
          class="scope-select"
          :placeholder="scopeKind === 'ledger' ? '选择账户' : '选择组合'"
          filterable
        >
          <el-option
            v-for="opt in scopeOptions"
            :key="opt.id"
            :label="opt.name"
            :value="opt.id"
          />
        </el-select>
        <span
          v-if="scopeKind !== 'family' && scopeOptions.length === 0"
          class="scope-empty"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          {{ scopeKind === "ledger" ? "暂无账户" : "暂无组合" }}
        </span>
      </div>
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
    <div v-if="scopeKind !== 'portfolio'" class="mb-6">
      <PnlCalendar
        :ledger-id="scopeKind === 'ledger' ? (scopeId ?? undefined) : undefined"
      />
    </div>
    <SoftBanner v-else class="mb-6" variant="info" icon="ep:info-filled">
      收益日历暂不支持组合口径——日/月/年三视图见「复盘」页家庭与账户档。
    </SoftBanner>

    <!-- #2135 区间收益归因（原生支持三级口径） -->
    <div class="mb-6">
      <PnlAttribution
        :ledger-id="scopeKind === 'ledger' ? (scopeId ?? undefined) : undefined"
        :portfolio-id="
          scopeKind === 'portfolio' ? (scopeId ?? undefined) : undefined
        "
      />
    </div>

    <!-- #2617 持仓结构（资产类别 / 股基分列 Top N / 集中度） -->
    <div class="mb-6">
      <PositionStructurePanel
        :ledger-id="scopeKind === 'ledger' ? (scopeId ?? undefined) : undefined"
        :portfolio-id="
          scopeKind === 'portfolio' ? (scopeId ?? undefined) : undefined
        "
      />
    </div>

    <!-- #870 持仓穿透（#2595 三级口径化；#2617 直接持有 / 穿透后双口径） -->
    <PenetrationPanel
      :ledger-id="scopeKind === 'ledger' ? (scopeId ?? undefined) : undefined"
      :portfolio-id="
        scopeKind === 'portfolio' ? (scopeId ?? undefined) : undefined
      "
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import PnlCalendar from "@/components/PnlCalendar/index.vue";
import PnlAttribution from "@/components/PnlAttribution/index.vue";
import PositionStructurePanel from "@/components/PositionStructurePanel/index.vue";
import PenetrationPanel from "@/components/PenetrationPanel/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
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

type ScopeKind = "family" | "ledger" | "portfolio";

const scopeKind = ref<ScopeKind>("family");
const scopeId = ref<number | null>(null);

const ledgers = ref<LedgerItem[]>([]);
const portfolios = ref<{ id: number; name: string }[]>([]);

const scopeOptions = computed(() =>
  scopeKind.value === "ledger"
    ? ledgers.value.map(l => ({ id: l.id, name: l.name }))
    : portfolios.value
);

// 切档位时清对象选择，避免「组合档残留账户 id」这类脏口径
watch(scopeKind, kind => {
  scopeId.value = null;
  if (kind !== "family") {
    void excessReload();
  }
});

// 选了具体对象才拉超额；切档或换对象都重取
watch(
  () => [scopeKind.value, scopeId.value] as const,
  ([kind, id]) => {
    if (kind === "family" || id != null) void excessReload();
  }
);

// ── #2134 区间表现 vs 基准（family / ledger / portfolio 三级全支持）─────────
const excess = ref<BenchmarkExcessResult | null>(null);

async function excessReload() {
  const params = { ...excessDateRange() } as {
    start_date: string;
    end_date: string;
    ledger_id?: number;
    portfolio_id?: number;
  };
  if (scopeKind.value === "ledger" && scopeId.value != null) {
    params.ledger_id = scopeId.value;
  } else if (scopeKind.value === "portfolio" && scopeId.value != null) {
    params.portfolio_id = scopeId.value;
  }
  try {
    const res = await getBenchmarkExcess(params);
    excess.value = res.data;
  } catch {
    // 诚实降级：整组「--」，不打断页面主体（与组合详情页同款约定）
    excess.value = null;
  }
}

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
  try {
    const res = await getLedgers();
    ledgers.value = res.data ?? [];
  } catch {
    ledgers.value = [];
  }
  try {
    const res = await getPortfolios();
    portfolios.value = res.data ?? [];
  } catch {
    portfolios.value = [];
  }
}

onMounted(() => {
  void loadScopeOptions();
  void excessReload(); // 家庭级首屏
});
</script>

<style scoped lang="scss">
.position-analysis {
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}

.scope-bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-compact);
  align-items: center;
}

.scope-select {
  min-width: 200px;
}

.scope-empty {
  font-size: var(--text-small);
}
</style>
