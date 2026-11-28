<!--
  ClearedCyclesSection · 清仓周期复盘（#2131 · 账本对齐 A' / #2774 补排行与时间范围）

  挂在「复盘」页（route /analysis）：该页定位是「时间维度上的表现：净值怎么走、
  收益从哪来」，而清仓周期回答的正是「已落袋的那部分表现从哪来」——同页不另开路由。

  数据：GET /api/summary/cleared-cycles/（只读现算）。本组件不算盈亏，只做
  「null 占位 + 排行取前 N + 档位转日期」；null 一律 "--"（部分配对周期不可算，不是 0）。

  与产品详情页 Pro 卡（ProductProPerformance · analytics/behavior.py）的分工：
  那边观察单位是 FIFO 卖出笔（单标的），这边是清仓周期（全账户列表+汇总），
  同一套后端 FIFO 口径，勿在本组件再造第二套。
-->
<template>
  <section>
    <!-- 标题收到 4 字（与侧边栏「菜单标题统一 4 字」同口径）：原标题 + 右侧计数
         + ⓘ 挤在一行，读起来像一句长句；计数降到徽标位 -->
    <SectionHeader title="清仓复盘" :info="sectionInfo">
      <template #action>
        <!-- 空态不写「0 只 · 0 个周期」：表里已经写了「暂无已清仓周期」，
             页头再报一次 0 只是噪音；而窗口筛到 0 时，页头那个 0 还会被误读成
             「一共就没清过仓」，掩盖了「换个范围就有」这个事实 -->
        <span v-if="summary.cycle_count > 0" class="cleared-cycles__count">
          {{ summary.product_count }} 只 · {{ summary.cycle_count }} 个周期
        </span>
      </template>
    </SectionHeader>

    <!-- 时间范围：切换后整块重算（汇总 / 排行 / 明细同一口径），故放在最上方统管全节 -->
    <div class="cleared-cycles__range">
      <SegmentedControl
        v-model="range"
        :options="CLEARED_RANGE_OPTIONS"
        size="small"
        aria-label="清仓周期时间范围"
        @change="load"
      />
    </div>

    <MetricGrid>
      <!-- 主数字统一 --brand-ink（WCAG AA：白底 5.86:1）；不用 --brand-700（3.73:1 不达标） -->
      <MetricCard
        title="累计已实现盈亏"
        :value="pnlTotalLabel"
        featured
        value-color="var(--brand-ink)"
        :caption="pnlTotalCaption(summary)"
      />
      <MetricCard
        title="胜率"
        :value="winRateLabel"
        unit="%"
        value-color="var(--brand-ink)"
        :caption="winRateCaptionText"
      />
      <MetricCard
        title="盈亏比"
        :value="ratioLabel"
        value-color="var(--brand-ink)"
        caption="平均盈利 / 平均亏损"
      />
      <MetricCard
        title="平均持有天数"
        :value="avgHoldingLabel"
        unit="天"
        value-color="var(--brand-ink)"
        caption="按周期简单平均"
      />
    </MetricGrid>

    <!-- 盈亏排行（#2774）：拆到 ClearedRankList —— 页面曾因它越过 400 行门槛 -->
    <ClearedRankList :cycles="cycles" />

    <!-- 明细表（含分页 / 排序 / 点产品进详情）：334 行不再一次性铺开 -->
    <ClearedCyclesTable :rows="cycles" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import { formatAmount } from "@/utils/currency";
import {
  getClearedCycles,
  type ClearedCycle,
  type ClearedCyclesSummary
} from "@/api/summary";
import {
  CLEARED_RANGE_OPTIONS,
  fmtHoldingDaysValue,
  fmtRatio,
  pnlTotalCaption,
  rangeStartDate,
  winRateCaption,
  type ClearedRangeKey
} from "./helpers";
import ClearedRankList from "./ClearedRankList.vue";
import ClearedCyclesTable from "./ClearedCyclesTable.vue";

defineOptions({ name: "ClearedCyclesSection" });

/** 零值汇总：初始态与请求失败态共用一份，避免两处字面量漂移（漏字段时 tsc 会报） */
const emptySummary = (): ClearedCyclesSummary => ({
  cycle_count: 0,
  product_count: 0,
  sample_count: 0,
  win_count: 0,
  loss_count: 0,
  win_rate: null,
  profit_loss_ratio: null,
  avg_holding_days: null,
  realized_pnl_total: null,
  total_trade_count: 0,
  // null = 没算（不是「一只都没亏」）；请求失败也退回「没算」，不假装健康
  unrealized_count: null,
  caveats: []
});

/** 账户级口径（2026-11-28，复盘页口径切换器）：不传 = 家庭级 */
const props = defineProps<{
  ledgerId?: number;
}>();

const cycles = ref<ClearedCycle[]>([]);
const range = ref<ClearedRangeKey>("all");
const summary = ref<ClearedCyclesSummary>(emptySummary());

/**
 * 请求序号：切档位比接口快时，慢返回的旧请求不能覆盖新结果
 * （否则「近一月」点完再点「投资以来」，可能停在近一月的数上）。
 */
let reqSeq = 0;

/** 接口失败：区块照常渲染空态（各区块独立降级，不阻塞复盘页其余内容） */
const load = async () => {
  const seq = ++reqSeq;
  try {
    const res = await getClearedCycles({
      ledger_id: props.ledgerId,
      start_date: rangeStartDate(range.value) ?? undefined,
      // 清仓后涨跌幅要额外查净值（锚点 + 最新），复盘页要看这列故显式开启（#2773）
      include_post_clear: true
    });
    if (seq !== reqSeq) return;
    const data = res?.data;
    cycles.value = data?.cycles ?? [];
    if (data?.summary) summary.value = data.summary;
  } catch {
    if (seq !== reqSeq) return;
    // 汇总必须一起清：只清明细会让「0 只 · 0 个周期」的卡片与空表并存，
    // 更糟的是切档位失败时卡片仍停在上一个档位的数字上——数字与筛选标签对不上，
    // 比空态更容易被当成真结论。宁可两者一致为空。
    cycles.value = [];
    summary.value = emptySummary();
  }
};

onMounted(load);

// 切档：清空再取（同 load 的 catch 分支理由——旧口径的数字配新标签比空态更坏）
watch(
  () => props.ledgerId,
  () => {
    cycles.value = [];
    summary.value = emptySummary();
    void load();
  }
);

const formatYuan = (n: number) => `¥${formatAmount(n || 0)}`;
const formatSignedYuan = (n: number) =>
  `${n >= 0 ? "+" : "-"}${formatYuan(Math.abs(n || 0))}`;

const pnlTotalLabel = computed(() =>
  summary.value.realized_pnl_total === null
    ? null
    : formatSignedYuan(summary.value.realized_pnl_total)
);
const winRateLabel = computed(() => fmtRatio(summary.value.win_rate));
const ratioLabel = computed(() => fmtRatio(summary.value.profit_loss_ratio));
const avgHoldingLabel = computed(() => {
  const days = fmtHoldingDaysValue(summary.value.avg_holding_days);
  return days === null ? null : String(days);
});
/** 胜率的限定条件（当前浮亏标的数）与胜率绑在一起，见 helpers.winRateCaption */
const winRateCaptionText = computed(() => winRateCaption(summary.value));

const sectionInfo = computed(() => {
  const s = summary.value;
  const base =
    "按「首买→末卖」周期统计已落袋表现：盈亏由 FIFO 配对自算（不读流水 realized_pnl 列，存量库该列全 0）；默认剔除货币基金/逆回购/现金；时间范围按末卖日裁剪；清仓后涨跌幅取累计净值（缺失回落单位净值），「--」表示算不出而非 0；胜率只含已清仓周期，套牢未卖的浮亏见胜率卡说明";
  if (s.cycle_count > s.sample_count) {
    return `${base}；${s.cycle_count - s.sample_count} 个周期因部分配对（先卖后买/无买入流水）不可算，未计入汇总`;
  }
  return base;
});
</script>

<style scoped>
.cleared-cycles__count {
  font-size: var(--el-font-size-small);
  color: var(--text-tertiary-ink);
}

.cleared-cycles__range {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--space-compact, 12px);
}
</style>
