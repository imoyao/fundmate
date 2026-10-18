<script setup lang="ts">
import { computed } from "vue";
import { ArrowDown, ArrowUp, Refresh } from "@element-plus/icons-vue";
import type { RealtimeQuotesReturn } from "@/composables/useRealtimeQuotes";
import type { ValuationSummary } from "@/utils/valuationEngine";
import SegmentedControl from "@/components/SegmentedControl/index.vue";

/**
 * 自选实时估值汇总条（状态指示 + 刷新档位 + 估值数据组），从 index.vue 抽出（2026-08-20）。
 * 2026-08-21 重构：原两行（状态行 + 汇总卡片行）合并为单行紧凑数据条
 * ——左侧状态与刷新频率、右侧三个汇总指标（总市值/总成本/总盈亏），去卡片背景，
 * 用细分隔线分区（design.md 数据密集场景紧凑原则），减少对下方表格的视线打断。
 * 仅展示用：realtime 实例由页面注入，本组件不发起任何请求。
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

<style scoped>
/* #1281 第二轮：从 --space-2(8) 回到 --space-3(12)。
   第一轮为压高度收到 8px，估值条与上下区块几乎贴在一起，整页失去呼吸感；
   现在的取舍是「留白回到规范档位 + 滚动时整条收起」，两种状态各自干净。 */

/* 下外边距逐步收紧：--space-3(12) → --space-2(8) → 4px（2026-09-05）。
   本条是「顶部第三层」，与头部行/横幅叠加吃掉的都是首屏行数；4px 已贴近下表格，
   靠底部分割线分区，视觉可接受。 */
.summary-bar {
  margin-bottom: var(--space-1);
}

/* 单行：左段状态+刷新（固定） / 右段汇总指标（弹性靠右）
   （多轮收紧后 padding 落定 4px：本条无卡片背景、靠细线分区，4px 呼吸足够） */
.summary-row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  justify-content: space-between;
  min-width: 0;
  padding: var(--space-1) 0;
}

.summary-row__status {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.summary-row__metrics {
  display: flex;
  flex-shrink: 0;
  gap: 12px;
  align-items: center;
}

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-trading {
  background: var(--color-rise);
}

.status-closed,
.status-idle {
  background: var(--text-secondary);
}

.status-error {
  background: var(--color-danger);
}

.status-text {
  font-size: var(--text-label);
  font-weight: 400;
  color: var(--text-secondary);
}

.update-time {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

/* 休市说明（#2338）：与状态文案同级字号，避免「少了一行」被读成数据出错。
   用 --text-secondary（5.77:1）而非 --text-tertiary —— 后者作正文不足 4.5:1。 */
.closed-hint {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
}

/* 刷新控件组：休市时整组置灰，tooltip 落在本包裹层（disabled 控件自身不派发事件） */
.refresh-controls {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}

/* 汇总指标紧凑数据组：label 12px 次级 + value 等宽数字，细分隔线分区 */
.metric-group {
  display: flex;
  gap: 4px;
  align-items: baseline;
  white-space: nowrap;
}

/* 汇总指标：#1281 第四轮整体降一档（label 12→11、value 14→13、主指标 18→16）。
   顶部右侧这三个数字曾占据很大一块视觉重量，与下方表格争抢注意力；
   降档后仍是「label + 等宽数字」结构，可读性不变，视觉重心回到列表。 */
.metric-label {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.metric-value {
  font-size: var(--text-label);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 主指标（总盈亏）：16px/800 视觉锚点，红涨绿跌走 --color-rise/--color-fall */
.metric-value--pnl {
  font-size: var(--text-body);
  font-weight: 800;
}

.metric-divider {
  flex-shrink: 0;
  width: 1px;
  height: 16px;
  background-color: var(--border-subtle);
}

/* 刷新图标按钮：无文字，loading 时由 EP 自带 loading 图标替代 */
.refresh-icon-btn {
  width: 28px;
  height: 28px;
  padding: 0;
}

.refresh-icon-btn:hover {
  color: var(--text-primary) !important;
}

.text-up {
  color: var(--color-rise-ink);
}

.text-down {
  color: var(--color-fall-ink);
}

.text-flat {
  color: var(--text-secondary);
}

.pct {
  font-size: var(--text-label);
  font-weight: 400;
  opacity: 0.8;
}
</style>
