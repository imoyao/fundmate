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
        <el-segmented
          :model-value="realtime.refreshInterval.value"
          class="refresh-segmented"
          :options="intervalOptions"
          @change="emit('interval-change', $event)"
        />
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
  margin-bottom: 12px;
}

/* 单行：左段状态+刷新（固定） / 右段汇总指标（弹性靠右） */
.summary-row {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
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

/* 刷新频率 segmented：24px 小胶囊（design.md「Segmented · 小尺寸」，与 SettingsDrawer 双处一致）。
   注意：必须带 group 100% 宽 + item flex:1 + justify-content:center——
   EP 的选中背景（.el-segmented__item-selected）是 JS 绝对定位块，item 若不均分/不居中会错位（胖/偏移）。 */
.refresh-segmented :deep(.el-segmented) {
  height: 24px;
  padding: 2px;
  background-color: var(--bg-muted);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

/* item 均分铺满整行：EP 默认 group/item 不拉伸，需显式声明 group 100% 宽 + item flex:1 */
.refresh-segmented :deep(.el-segmented__group) {
  display: flex;
  width: 100%;
}

.refresh-segmented :deep(.el-segmented__item) {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  height: 20px;
  padding: 0 10px;
  font-size: 12px;
  line-height: 20px;
  color: var(--text-secondary);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

.refresh-segmented :deep(.el-segmented__item:hover) {
  color: var(--text-primary);
}

.refresh-segmented :deep(.el-segmented__item.is-selected) {
  color: var(--brand-700);
  background-color: var(--brand-100);
  box-shadow: none;
}

.refresh-segmented :deep(.el-segmented__item.is-selected:hover) {
  background-color: var(--brand-200);
}

/* EP 选中态背景是独立子元素（默认白底+阴影），一并覆盖为品牌软按钮色 */
.refresh-segmented :deep(.el-segmented__item-selected) {
  background-color: var(--brand-100);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

.refresh-segmented
  :deep(.el-segmented__item.is-selected:hover .el-segmented__item-selected) {
  background-color: var(--brand-200);
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
