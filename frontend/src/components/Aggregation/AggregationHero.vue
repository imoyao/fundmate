<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import AggregationBreakdownDonut from "@/components/Aggregation/AggregationBreakdownDonut.vue";
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
 *
 * 资产构成环形图（#1224）已拆为 `AggregationBreakdownDonut`（#980），
 * 本组件只负责整体构图与左右两栏。
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
    <AggregationBreakdownDonut :items="typeBreakdown" />

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
  gap: var(--space-5, 24px);
  align-items: center;
  justify-content: space-between;
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
  font-size: var(--text-label);
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

/* ── 右侧：统计信息色块 ── */
.hero-right {
  display: flex;
  flex: none;
  flex-wrap: wrap;
  gap: var(--space-3, 12px);
  align-items: center;
}

.stat-block {
  display: flex;
  gap: 10px;
  align-items: center;
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
  flex: none;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: var(--bg-card);
  border-radius: var(--radius-sm, 6px);
}

.stat-icon {
  font-size: var(--text-body);
  color: var(--brand-500, #f69988);
}

.stat-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.stat-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.stat-value {
  font-size: var(--text-num-strong);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.stat-hint {
  flex: none;
  margin-left: 4px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  opacity: 0.5;
}

@media (width <= 768px) {
  .hero {
    flex-direction: column;
    gap: var(--space-compact);
    align-items: stretch;
    padding: var(--space-5, 24px) var(--space-compact);
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
