<!--
  MetricDetailTable · 全部市场温度指标紧凑表格
  从 temperature/index.vue 拆分（#980），模板与相关样式随组件 scoped 迁移。
  内部复用 utils/temperatureFormat 的 displaySource / formatValue / valueColorClass。
-->
<template>
  <section class="cards-section">
    <SectionHeader title="全部市场温度指标" />
    <div class="metric-table">
      <div class="metric-table-head">
        <span class="col-name">指标</span>
        <span class="col-source">来源</span>
        <span class="col-value">数值</span>
        <span class="col-label">等级</span>
      </div>
      <div
        v-for="item in items"
        :key="`${item.source}-${item.name}`"
        class="metric-table-row"
        :class="{ stale: item.stale }"
      >
        <div class="col-name">
          <span class="metric-name-text">{{ item.name }}</span>
          <el-tooltip v-if="item.note" :content="item.note" placement="top">
            <el-icon class="info-icon"><Info-Filled /></el-icon>
          </el-tooltip>
        </div>
        <div class="col-source">
          <span class="source-tag">{{ displaySource(item.source) }}</span>
        </div>
        <div class="col-value" :class="valueColorClass(item.value, item.label)">
          {{ formatValue(item.value) }}{{ item.unit || "" }}
        </div>
        <div class="col-label">
          <TemperatureLevelBadge :level="item.label" size="sm" />
        </div>
      </div>
      <div v-if="!items.length" class="empty-state">暂无更多指标</div>
    </div>
  </section>
</template>

<script setup lang="ts">
import SectionHeader from "@/components/SectionHeader/index.vue";
import TemperatureLevelBadge from "@/components/TemperatureLevelBadge/index.vue";
import { InfoFilled } from "@element-plus/icons-vue";
import {
  displaySource,
  formatValue,
  valueColorClass
} from "@/utils/temperatureFormat";

defineOptions({ name: "MetricDetailTable" });

withDefaults(
  defineProps<{
    /** 全部单值指标列表（已过滤核心指标，含 source / name / value / unit / label / note / stale 字段） */
    items?: any[];
  }>(),
  {
    items: () => []
  }
);
</script>

<style lang="scss" scoped>


/* ===== 响应式（自 temperature/index.vue 迁移） ===== */
@media (width <= 768px) {
  .metric-table-head,
  .metric-table-row {
    grid-template-columns: 2fr 80px 80px;
    gap: 8px;
    padding: 10px 12px;
  }

  .metric-table-head .col-source,
  .metric-table-row .col-source {
    display: none;
  }
}

.cards-section {
  margin-bottom: 24px;
}

.metric-table {
  overflow: hidden;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.metric-table-head,
.metric-table-row {
  display: grid;
  grid-template-columns: 2fr 1fr 100px 100px;
  gap: 12px;
  align-items: center;
  padding: 12px 16px;
}

.metric-table-head {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: var(--bg-subtle);
}

.metric-table-row {
  font-size: 13px;
  border-top: 1px solid var(--border-light);
  transition: background 0.12s ease;
}

.metric-table-row:hover {
  background: var(--bg-subtle);
}

.metric-table-row.stale {
  opacity: 0.6;
}

.metric-table-row.stale .col-value {
  text-decoration: line-through;
}

.col-name {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

.metric-name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.info-icon {
  flex-shrink: 0;
  color: var(--text-tertiary);
  cursor: help;
}

.col-source {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.source-tag {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: 6px;
}

.col-value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.col-label {
  text-align: right;
}

.empty-state {
  padding: 40px 0;
  font-size: 14px;
  color: var(--text-tertiary);
  text-align: center;
}

/* ===== 指标数值颜色（val-* 令牌） ===== */
.val-high {
  color: var(--temp-high);
}

.val-low {
  color: var(--temp-low);
}

.val-mid {
  color: var(--text-secondary);
}

/* ===== 全部指标紧凑表格区块（自 temperature/index.vue 迁移） ===== */
</style>
