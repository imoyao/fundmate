<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getCssVar, getChartPalette } from "@/composables/echarts/theme";
import type { AggregationTypeBreakdownItem } from "@/api/ledger";

/**
 * 聚合视图顶部汇总区（#1101 场外基金 / #1132 场内证券 共用）。
 *
 * #1133 定稿：克制卡片式设计，与页面其它区块同一视觉语言。
 * 水平布局（左大数字 + 右统计信息），充分利用卡片宽度避免右侧空白。
 *
 * 层级建立方式：
 *   1. 金额数字用品牌强调色 —— 区块内唯一强色
 *   2. 元信息用色块承载 —— 图标 + 标签 + 值，视觉上突出但不抢戏
 */
defineOptions({ name: "AggregationHero" });

const props = withDefaults(
  defineProps<{
    totalYuan: number;
    snapshotDate?: string | null;
    snapshotDateLatest?: string | null;
    hasSnapshotGap?: boolean;
    /** 🔄 NavService 净值日期（与 snapshot_date 分叉时可双日期展示） */
    navDate?: string | null;
    label?: string;
    count?: number | null;
    /** 资产构成：按基金类型聚合的市值分布（有数据时在卡片内展示环形图占比） */
    typeBreakdown?: AggregationTypeBreakdownItem[] | null;
  }>(),
  {
    snapshotDate: null,
    snapshotDateLatest: null,
    hasSnapshotGap: false,
    navDate: null,
    label: "总资产",
    count: null,
    typeBreakdown: null
  }
);

const dateTooltip = computed(() => {
  const base = "数据日期取自账户导入时的份额日期，代表该持仓记录的时间点。";
  if (props.hasSnapshotGap && props.snapshotDateLatest) {
    return `${base}各账户导入时间不同，此处展示最早的一笔（${formatDisplayDate(props.snapshotDate)}），最近的一笔为 ${formatDisplayDate(props.snapshotDateLatest)}。`;
  }
  return base;
});

const amountTooltip = computed(
  () => `${props.label}为当前全部持仓的市值合计，按最新参考净值计算。`
);

function formatDisplayDate(d: string | null): string {
  if (!d) return "";
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${parseInt(m[2], 10)}月${parseInt(m[3], 10)}日` : d;
}

// ── 资产构成环形图（#1224：按基金类型展示市值占比）──
/** 过滤市值为 0 的构成项（避免空持仓画出无意义扇区） */
const breakdownItems = computed<AggregationTypeBreakdownItem[]>(() =>
  (props.typeBreakdown ?? []).filter(x => (x.market_value_cents || 0) > 0)
);
const hasBreakdown = computed(() => breakdownItems.value.length > 0);
const breakdownTotal = computed(() =>
  breakdownItems.value.reduce((sum, x) => sum + x.market_value_cents, 0)
);
/** 图例只列前 5 类，其余折叠为「其他」 */
const legendTop = computed(() => breakdownItems.value.slice(0, 5));
const restCount = computed(() => Math.max(0, breakdownItems.value.length - 5));
const restTotal = computed(() =>
  breakdownItems.value
    .slice(5)
    .reduce((sum, x) => sum + x.market_value_cents, 0)
);

function pctOf(cents: number): string {
  const total = breakdownTotal.value;
  return total > 0 ? ((cents / total) * 100).toFixed(1) : "0";
}

/** 8 色分类配色板（实时读 CSS 语义变量，design.md 红线：禁止硬编码 hex） */
const donutPalette = getChartPalette();

const donutOption = computed(() => {
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return {
    animation: !reduceMotion,
    tooltip: {
      trigger: "item",
      backgroundColor: getCssVar("--bg-card") || "#ffffff",
      borderColor: getCssVar("--border-light") || "#f0ebe4",
      textStyle: {
        color: getCssVar("--text-primary") || "#2d2a24",
        fontSize: 12
      },
      formatter: (params: any) => {
        const pct = pctOf((params.value as number) * 100);
        return `${params.name}<br/>¥${Number(params.value).toLocaleString()}（${pct}%）`;
      }
    },
    series: [
      {
        type: "pie",
        radius: ["58%", "80%"],
        center: ["50%", "50%"],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 6,
          borderColor: getCssVar("--bg-card") || "#ffffff",
          borderWidth: 2
        },
        label: { show: false },
        emphasis: { scaleSize: 4 },
        data: breakdownItems.value.map((x, i) => ({
          name: x.name,
          value: x.market_value_cents / 100,
          itemStyle: { color: donutPalette[i % donutPalette.length] }
        }))
      }
    ]
  };
});
</script>

<template>
  <div class="hero">
    <!-- 左侧：主指标 -->
    <div class="hero-left">
      <p class="hero-label">{{ label }}</p>
      <el-tooltip placement="bottom-start" :content="amountTooltip">
        <div class="hero-amount">
          <MoneyDisplay
            :value="totalYuan"
            size="xl"
            :show-sign="false"
            :auto-color="false"
          />
        </div>
      </el-tooltip>
    </div>

    <!-- 资产构成环形图：仅在有类型分布数据时展示（#1224） -->
    <div v-if="hasBreakdown" class="hero-donut-block">
      <div class="hero-donut">
        <v-chart :option="donutOption" :autoresize="true" class="donut-chart" />
        <div class="donut-center">
          <span class="donut-center-label">资产构成</span>
          <span class="donut-center-count">{{ breakdownItems.length }} 类</span>
        </div>
      </div>
      <div class="hero-legend">
        <div
          v-for="(item, i) in legendTop"
          :key="item.name"
          class="legend-item"
          :title="`¥${(item.market_value_cents / 100).toLocaleString()}`"
        >
          <span
            class="legend-dot"
            :style="{ background: donutPalette[i % donutPalette.length] }"
          />
          <span class="legend-name">{{ item.name }}</span>
          <span class="legend-pct">{{ pctOf(item.market_value_cents) }}%</span>
        </div>
        <div v-if="restCount > 0" class="legend-item">
          <span class="legend-dot legend-dot--rest" />
          <span class="legend-name">其他 {{ restCount }} 类</span>
          <span class="legend-pct">{{ pctOf(restTotal) }}%</span>
        </div>
      </div>
    </div>

    <!-- 右侧：元信息色块 -->
    <div class="hero-right">
      <el-tooltip v-if="snapshotDate" placement="top" :content="dateTooltip">
        <div class="stat-block">
          <div class="stat-icon-wrap">
            <IconifyIconOffline icon="ep:calendar" class="stat-icon" />
          </div>
          <div class="stat-body">
            <span class="stat-label">数据日期</span>
            <span class="stat-value">{{
              formatDisplayDate(snapshotDate)
            }}</span>
          </div>
          <IconifyIconOffline
            v-if="hasSnapshotGap"
            icon="ep:info-filled"
            class="stat-hint"
          />
        </div>
      </el-tooltip>

      <div v-if="count != null" class="stat-block">
        <div class="stat-icon-wrap">
          <IconifyIconOffline icon="ep:box" class="stat-icon" />
        </div>
        <div class="stat-body">
          <span class="stat-label">持仓项数</span>
          <span class="stat-value">{{ count }} 项</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-5, 24px);
  padding: var(--space-5, 24px) var(--space-standard, 18px);
  font-variant-numeric: tabular-nums;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg, 16px);
  box-shadow: var(--shadow-raised);
}

/* ── 左侧：大数字锚点 ── */
.hero-left {
  min-width: 0;
}

.hero-label {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.hero-amount {
  cursor: default;
}

/* 品牌强调色：区块内唯一强色 */
.hero-amount :deep(.money-display) {
  color: var(--brand-600, #f06b57) !important;
}

/* ── 资产构成环形图（#1224）── */
.hero-donut-block {
  display: flex;
  align-items: center;
  gap: var(--space-4, 16px);
  flex: none;
}

.hero-donut {
  position: relative;
  width: 148px;
  height: 148px;
  flex: none;
}

.donut-chart {
  position: absolute;
  inset: 0;
}

.donut-center {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  pointer-events: none;
  transform: translate(-50%, -50%);
}

.donut-center-label {
  font-size: 11px;
  color: var(--text-tertiary);
}

.donut-center-count {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.hero-legend {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.legend-item {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  line-height: 1.2;
  white-space: nowrap;
}

.legend-dot {
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 50%;
}

.legend-dot--rest {
  background: var(--text-tertiary);
  opacity: 0.5;
}

.legend-name {
  color: var(--text-secondary);
}

.legend-pct {
  min-width: 44px;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  text-align: right;
  color: var(--text-primary);
}

/* ── 右侧：统计信息色块 ── */
.hero-right {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3, 12px);
  align-items: center;
  flex: none;
}

.stat-block {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: default;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md, 10px);
  transition: border-color 0.2s ease;
}

.stat-block:hover {
  border-color: var(--brand-300, var(--border-default));
}

.stat-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex: none;
  background: var(--bg-card);
  border-radius: var(--radius-sm, 6px);
}

.stat-icon {
  font-size: 15px;
  color: var(--brand-500, #f69988);
}

.stat-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.stat-label {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.stat-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.stat-hint {
  flex: none;
  margin-left: 4px;
  font-size: 13px;
  color: var(--text-tertiary);
  opacity: 0.5;
}

@media (width <= 768px) {
  .hero {
    flex-direction: column;
    align-items: stretch;
    gap: var(--space-4, 16px);
    padding: var(--space-5, 24px) var(--space-4, 16px);
  }

  .hero-donut-block {
    justify-content: center;
  }

  .hero-right {
    justify-content: flex-start;
  }

  .stat-block {
    flex: 1 1 calc(50% - 6px);
    min-width: 140px;
  }
}
</style>
