<script setup lang="ts">
import { computed } from "vue";
import { ArrowDown, ArrowUp, Refresh } from "@element-plus/icons-vue";
import type { RealtimeQuotesReturn } from "@/composables/useRealtimeQuotes";
import type { ValuationSummary } from "@/utils/valuationEngine";
import type { DayPnlSummary } from "./dayPnl";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import ValuationSourceBadge from "@/components/ValuationSourceBadge/index.vue";
import { ESTIMATE_DISCLAIMER } from "@/composables/usePositionValuation";

/**
 * 自选实时估值汇总条（状态指示 + 刷新档位 + 估值数据组），从 index.vue 抽出（2026-08-20）。
 * 2026-08-21 重构：原两行（状态行 + 汇总卡片行）合并为单行紧凑数据条
 * ——左侧状态与刷新频率、右侧三个汇总指标（总市值/总成本/总盈亏），去卡片背景，
 * 用细分隔线分区（design.md 数据密集场景紧凑原则），减少对下方表格的视线打断。
 * 仅展示用：realtime 实例由页面注入，本组件不发起任何请求。
 *
 * 2026-11-05：「当日盈亏」拆成「今日估算 / 昨日盈亏」两个指标（与表格两列同名同口径），
 * 样式同时外置到 `watchlistSummaryBar.css` 以守住 .vue 行数门禁（见该 CSS 文件头）。
 */
const props = defineProps<{
  realtime: RealtimeQuotesReturn;
  refreshing: boolean;
  /**
   * 未开启实时时的静态价汇总（页面注入；null 表示确实没有可展示的数据）。
   *
   * 为什么需要它：本条常驻展示（不再 `v-if` 实时开关），而静态价
   * （最近交易日收盘价 / 确认净值）在后端已是权威口径，不该因为没开实时
   * 就把「总市值 / 总成本 / 总盈亏」整块抹掉（2026-09-22 用户反馈）。
   */
  fallbackSummary?: ValuationSummary | null;
  /**
   * 当日盈亏（2026-11-06 升级为真实值优先、估值兜底）：`(T 价 − T-1 确认价) × 份额`，
   * 与表格「当日盈亏」列**同源**（`dayPnl.ts`，比例按基准市值加权，
   * 不是各行涨跌幅的算术平均）。`status` 字段标记这一行（或汇总）是否仍是估值态。
   *
   * `value == null` = 一条都算不出（未开实时 / 休市 / 行情不可达）→ 整块不渲染。
   * ⚠️ 绝不拿「昨日盈亏」填这里：那正是用户反馈的「盘中看到昨天的真实值」。
   * 也不显示 `0.00` —— 会让人以为「今天没赚没亏」，同样是假象。
   */
  todayEstimate?: DayPnlSummary | null;
  /**
   * 昨日盈亏（2026-11-05）：`(T-1 确认价 − T-2 确认价) × 份额`，
   * 已确认的真实值，与实时通道无关，盘中不跳动。与表格「昨日盈亏」列同源。
   * 这正是 #2640 那列**实际算出来的数**，此前被误命名为「当日盈亏」。
   */
  yesterdayPnl?: DayPnlSummary | null;
}>();

const emit = defineEmits<{
  (e: "interval-change", value: string | number | boolean): void;
  (e: "manual-refresh"): void;
}>();

/** 实时汇总优先；未开实时（summary 为空）时用注入的静态汇总兜底 */
const summary = computed(
  () => props.realtime.summary.value ?? props.fallbackSummary ?? null
);

/** 状态文案：idle 专指「未开启实时」，与休市/收盘区分开 */
const statusText = computed(() => {
  const status = props.realtime.status.value;
  if (status === "trading") return "实时行情";
  if (status === "idle") return "静态价（未开启实时）";
  return "休市/收盘";
});

/**
 * 休市 / 收盘（#2338）：此时 `manualRefresh()` 与轮询 tick 都会被 `canFetch()`
 * 挡下，点了也不会取数。两个控件继续可点就是「静默无反应」，用户只会理解成
 * 「数据坏了」——故整组置灰 + 给出为什么，而不是让它看起来能点。
 *
 * 只认 `closed`（休市/收盘）：`idle`（用户主动关实时）时整组本来就 v-if 掉不渲染，
 * `error`（交易日历接口之外的原因取数失败）**不禁用** —— 那种情况下手动刷新正是
 * 用户自救的手段，禁用等于把故障坐实。
 */
const marketClosed = computed(() => props.realtime.status.value === "closed");

/** 置灰控件的原因说明：tooltip（鼠标）+ aria-label（读屏）共用一份文案 */
const closedHint = "休市 / 收盘：暂停抓取实时估值，下方为最近已确认净值";
const hasValid = computed(
  () => !!summary.value && (summary.value.totalMarketValue ?? 0) > 0
);
const profitClass = computed(() => {
  const v = summary.value?.totalPnl ?? 0;
  if (v > 0) return "text-up";
  if (v < 0) return "text-down";
  return "text-flat";
});
const profitArrow = computed(() =>
  (summary.value?.totalPnl ?? 0) >= 0 ? ArrowUp : ArrowDown
);

/**
 * 两列盈亏（2026-11-05 拆列）与总盈亏共用同一套涨跌配色 / 箭头：
 * 同一屏不出现两套语义。
 *
 * 用无状态纯函数而不是给每列复制三份 computed —— 拆成两列后，复制粘贴最容易
 * 漏掉「value == null 就整块不渲染」这条守卫，把 `—` 显示成 `0.00`。
 * props 在模板里每次渲染读取，响应式由 Vue 模板自身保证，无需手工包 computed。
 */
const hasTodayEstimate = computed(() => props.todayEstimate?.value != null);
const hasYesterdayPnl = computed(() => props.yesterdayPnl?.value != null);

function pnlClass(v: number | null | undefined): string {
  if (v == null || v === 0) return "text-flat";
  return v > 0 ? "text-up" : "text-down";
}
function pnlArrow(v: number | null | undefined) {
  return (v ?? 0) >= 0 ? ArrowUp : ArrowDown;
}
const intervalOptions = [
  { label: "15s", value: 15 },
  { label: "30s", value: 30 },
  { label: "60s", value: 60 },
  { label: "90s", value: 90 }
];
</script>

<template>
  <div class="summary-bar">
    <div class="summary-row">
      <!-- 左段：状态指示 + 刷新档位（固定） -->
      <div class="summary-row__status">
        <span class="status-dot" :class="`status-${realtime.status.value}`" />
        <span class="status-text">{{ statusText }}</span>
        <span v-if="realtime.lastUpdateTime.value" class="update-time">
          更新于 {{ realtime.lastUpdateTime.value }}
        </span>
        <!-- 刷新档位与手动刷新都只对实时轮询有意义：未开启实时时整体不渲染，
             避免点了没反应（manualRefresh 在 enabled=false 时直接 return） -->
        <span v-if="marketClosed" class="closed-hint">
          休市不抓取 · 数值为已确认净值
        </span>
        <template v-if="realtime.enabled.value">
          <!-- 刷新档位与手动刷新：休市时整组置灰（#2338）。
               两者 disabled 后不再派发鼠标事件，tooltip 必须落在外层包裹元素上，
               否则「为什么点不了」对用户完全不可见。 -->
          <el-tooltip
            :disabled="!marketClosed"
            :content="closedHint"
            placement="bottom"
          >
            <span class="refresh-controls">
              <SegmentedControl
                :model-value="realtime.refreshInterval.value"
                :options="intervalOptions"
                :disabled="marketClosed"
                size="small"
                :aria-label="
                  marketClosed ? `刷新频率（${closedHint}）` : '刷新频率'
                "
                @change="emit('interval-change', $event)"
              />
              <el-button
                text
                circle
                :loading="refreshing"
                :disabled="marketClosed"
                :aria-label="
                  marketClosed
                    ? `手动刷新行情（${closedHint}）`
                    : '手动刷新行情'
                "
                class="refresh-icon-btn"
                :style="{ color: 'var(--text-secondary)' }"
                @click="emit('manual-refresh')"
              >
                <el-icon v-if="!refreshing"><Refresh /></el-icon>
              </el-button>
            </span>
          </el-tooltip>
        </template>
      </div>

      <!-- 右段：汇总指标紧凑数据组（无卡片背景，label + value + 细分隔线） -->
      <div v-if="hasValid" class="summary-row__metrics">
        <div class="metric-group">
          <span class="metric-label">总市值</span>
          <span class="metric-value">{{
            summary?.totalMarketValue?.toFixed(2)
          }}</span>
        </div>
        <span class="metric-divider" />
        <div class="metric-group">
          <span class="metric-label">总成本</span>
          <span class="metric-value">{{ summary?.totalCost?.toFixed(2) }}</span>
        </div>
        <span class="metric-divider" />
        <!-- 当日盈亏 / 昨日盈亏（2026-11-05 拆列，2026-11-06 升级为真实值优先、估值兜底）：
             与表格两列同名同口径。一个今天（真实值优先、未确认用估值填充、盘中随轮询跳动）、
             一个昨天（已确认、不跳动），并排才分得清。两者都「有值才显示」：拿不到实时行情时
             当日盈亏整块不渲染，绝不拿昨日数字顶替，也不显示 0.00 那种「没赚没亏」的假象。 -->
        <template v-if="hasTodayEstimate">
          <div class="metric-group metric-group--pnl">
            <span class="metric-label">当日盈亏</span>
            <!-- 「估」徽章：与表格「当日盈亏」列同一个 ValuationSourceBadge，
                 免责文案走 ESTIMATE_DISCLAIMER 单一出口。仅估值态出现（已确认真实值不挂），
                 避免把确认值也读成估算。 -->
            <el-tooltip
              v-if="todayEstimate?.status === 'estimated'"
              :content="ESTIMATE_DISCLAIMER"
              placement="top"
            >
              <ValuationSourceBadge
                status="estimated"
                size="sm"
                :tip="ESTIMATE_DISCLAIMER"
              />
            </el-tooltip>
            <span
              class="metric-value metric-value--pnl"
              :class="pnlClass(todayEstimate?.value)"
            >
              <el-icon
                ><component :is="pnlArrow(todayEstimate?.value)"
              /></el-icon>
              {{ todayEstimate?.value?.toFixed(2) }}
              <span v-if="todayEstimate?.ratio != null" class="pct"
                >({{ todayEstimate?.ratio?.toFixed(2) }}%)</span
              >
            </span>
          </div>
          <span class="metric-divider" />
        </template>
        <template v-if="hasYesterdayPnl">
          <div class="metric-group metric-group--pnl">
            <span class="metric-label">昨日盈亏</span>
            <span
              class="metric-value metric-value--pnl"
              :class="pnlClass(yesterdayPnl?.value)"
            >
              <el-icon
                ><component :is="pnlArrow(yesterdayPnl?.value)"
              /></el-icon>
              {{ yesterdayPnl?.value?.toFixed(2) }}
              <span v-if="yesterdayPnl?.ratio != null" class="pct"
                >({{ yesterdayPnl?.ratio?.toFixed(2) }}%)</span
              >
            </span>
          </div>
          <span class="metric-divider" />
        </template>
        <!-- 主指标（总盈亏）：放大加粗 + 红涨绿跌（design.md 视觉锚点，规范 595） -->
        <div class="metric-group metric-group--pnl">
          <span class="metric-label">总盈亏</span>
          <span class="metric-value metric-value--pnl" :class="profitClass">
            <el-icon><component :is="profitArrow" /></el-icon>
            {{ summary?.totalPnl?.toFixed(2) }}
            <span class="pct"
              >({{ summary?.totalPnlPercent?.toFixed(2) }}%)</span
            >
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="./watchlistSummaryBar.css"></style>
