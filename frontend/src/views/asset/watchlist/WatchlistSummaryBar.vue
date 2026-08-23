<script setup lang="ts">
import { computed } from "vue";
import { ArrowDown, ArrowUp, Refresh } from "@element-plus/icons-vue";
import type { RealtimeQuotesReturn } from "@/composables/useRealtimeQuotes";

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
}>();

const emit = defineEmits<{
  (e: "interval-change", value: string | number | boolean): void;
  (e: "manual-refresh"): void;
}>();

const summary = computed(() => props.realtime.summary.value);
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
        <span class="status-text">
          {{ realtime.status.value === "trading" ? "实时行情" : "休市/收盘" }}
        </span>
        <span v-if="realtime.lastUpdateTime.value" class="update-time">
          更新于 {{ realtime.lastUpdateTime.value }}
        </span>
        <!-- 刷新档位：手写分段控制器（弃用 el-segmented：其 JS 绝对定位选中滑块与
             自定义 item 尺寸错位，曾出现选中块偏高/hover 半截/文字偏上，见 OcrImportModal 同款决策）。
             选中态仅浅红底 + 深红字；轨道用 --bg-soft 暖米色衬托 --brand-100（近白）选中底 -->
        <div class="refresh-segmented" role="tablist" aria-label="刷新频率">
          <button
            v-for="opt in intervalOptions"
            :key="opt.value"
            type="button"
            role="tab"
            class="refresh-segmented__item"
            :class="{
              'is-active': realtime.refreshInterval.value === opt.value
            }"
            :aria-selected="realtime.refreshInterval.value === opt.value"
            @click="emit('interval-change', opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
        <el-button
          text
          circle
          :loading="refreshing"
          aria-label="手动刷新行情"
          class="refresh-icon-btn"
          :style="{ color: 'var(--text-secondary)' }"
          @click="emit('manual-refresh')"
        >
          <el-icon v-if="!refreshing"><Refresh /></el-icon>
        </el-button>
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
.summary-bar {
  /* design.md 间距体系：筛选栏/数据条区块间距 --space-compact(16px)，
     原写死 12px 在实时估值关闭（banner 隐藏）时与表格贴得过近，缺呼吸感 */
  margin-bottom: var(--space-compact);
}

/* 单行：左段状态+刷新（固定） / 右段汇总指标（弹性靠右）。
   上下 padding 给状态行自身留呼吸空间（休市态内容少时不显局促） */
.summary-row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  justify-content: space-between;
  min-width: 0;
  padding: var(--space-2) 0;
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
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary);
}

.update-time {
  font-size: 12px;
  color: var(--text-secondary);
}

/* 汇总指标紧凑数据组：label 12px 次级 + value 等宽数字，细分隔线分区 */
.metric-group {
  display: flex;
  gap: 4px;
  align-items: baseline;
  white-space: nowrap;
}

.metric-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.metric-value {
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 主指标（总盈亏）：18px/800 视觉锚点，红涨绿跌走 --color-rise/--color-fall */
.metric-value--pnl {
  font-size: 18px;
  font-weight: 800;
}

.metric-divider {
  flex-shrink: 0;
  width: 1px;
  height: 16px;
  background-color: var(--border-subtle);
}

/* ===== 刷新档位分段控制器（手写，弃用 el-segmented） =====
   轨道 --bg-soft 暖米色：--brand-100（#fff5f3 近白）选中底在灰轨道上不可见，
   暖米色轨道才能衬托出选中胶囊；item 统一高度，hover/选中同一几何尺寸，
   文字用 flex 居中（不用 line-height 撑高），杜绝「选中偏高/hover 半截/文字偏上」 */
.refresh-segmented {
  display: flex;
  gap: 2px;
  padding: 2px;
  background-color: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.refresh-segmented__item {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 20px;
  padding: 0 10px;
  font-size: 12px;
  line-height: 1;
  color: var(--text-secondary);
  cursor: pointer;
  background-color: transparent;
  border: none;
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

/* 原生 button 点击后收掉浏览器默认 focus 外框；键盘导航保留细描边兜底 */
.refresh-segmented__item:focus {
  outline: none;
}

.refresh-segmented__item:focus-visible {
  outline: 1px solid var(--brand-400);
  outline-offset: 1px;
}

/* hover 与选中同尺寸、同层级：仅底色深浅递进（透明 → --bg-hover → --brand-100），不再互相打架 */
.refresh-segmented__item:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

.refresh-segmented__item.is-active {
  font-weight: 600;
  color: var(--brand-700);
  background-color: var(--brand-100);
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
  color: var(--color-rise);
}

.text-down {
  color: var(--color-fall);
}

.text-flat {
  color: var(--text-secondary);
}

.pct {
  font-size: 12px;
  font-weight: 400;
  opacity: 0.8;
}
</style>
