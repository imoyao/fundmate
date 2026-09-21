<!--
  MetricDetailTable · 全部市场温度指标表格
  从 temperature/index.vue 拆分（#980）。

  2026-09-12：由自写 div grid 改为 <el-table>。
  原实现在页面内自绘表头 / 行 / 边框，绕过了 frontend/src/style/el-table.css
  定义的全站表格基线。该文件明确要求「所有 el-table 走全局基线，
  禁止各页面 ::deep(.el-table) 里自行覆盖，否则会重新分化出多套表格风格；
  新增页面表格直接用 <el-table> 即可自动继承基线，无需任何样式代码」。
  自绘结果就是本表与同页 BiasTable / CrowdingTable 视觉不一致（边框、表头底色、
  行高、hover 全都各写一套）。改为 el-table 后三张表共享同一基线。
  内部复用 utils/temperatureFormat 的 displaySource / formatValue / valueColorClass。
-->
<template>
  <CardBlock class="cards-section">
    <SectionHeader title="全部市场温度指标" />
    <el-table
      :data="items"
      border
      style="width: 100%"
      max-height="520"
      :row-class-name="rowClassName"
    >
      <el-table-column prop="name" label="指标" min-width="200">
        <template #default="{ row }">
          <div class="metric-name-cell">
            <span class="metric-name-text">{{ row.name }}</span>
            <el-tooltip v-if="row.note" :content="row.note" placement="top">
              <el-icon class="info-icon"><Info-Filled /></el-icon>
            </el-tooltip>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="来源" width="130">
        <template #default="{ row }">
          <span class="source-tag">{{ displaySource(row.source) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="数值" width="120" align="right">
        <template #default="{ row }">
          <span
            class="metric-value"
            :class="[
              valueColorClass(row.value, row.label),
              { stale: row.stale }
            ]"
            >{{ formatValue(row.value) }}{{ row.unit || "" }}</span
          >
        </template>
      </el-table-column>

      <el-table-column label="等级" width="150" align="right">
        <template #default="{ row }">
          <TemperatureLevelBadge :level="row.label" size="sm" />
        </template>
      </el-table-column>

      <template #empty>
        <div class="empty-state">暂无更多指标</div>
      </template>
    </el-table>
  </CardBlock>
</template>

<script setup lang="ts">
import CardBlock from "@/components/CardBlock/index.vue";
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

/** 数据滞后行：整行降透明度，与 BiasTable / CrowdingTable 的「滞后」语义一致。
 *  属 el-table.css 规则 3 允许保留的「行内行为」样式，不涉及视觉基线。 */
const rowClassName = ({ row }: { row: any }) => (row?.stale ? "is-stale" : "");
</script>

<style lang="scss" scoped>
/* 区块外壳统一走 CardBlock（#1547 T3.1 收敛），此处只留区块间距。
   外壳由 CardBlock 提供：--bg-card + --border-light + --radius-lg + --shadow-raised
   + --space-standard（24px）内边距，与 BiasTable / CrowdingTable 同规范。 */
.cards-section {
  margin-bottom: 24px;
}

.metric-name-cell {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

.metric-name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  white-space: nowrap;
}

.info-icon {
  flex-shrink: 0;

  /* audit-text-contrast: exempt 非文本图形（图标字形），按 WCAG 1.4.11 需 3:1，本令牌在页底 / 卡片底实测 3.57~3.69:1，达标；
     若改用 -ink 会与相邻正文同权，反而压平层级。登记见 docs/spec/tech-debt.md（#1586） */
  color: var(--text-tertiary);
  cursor: help;
}

/* 来源小标签：仅作来源标注，视觉与全站胶囊族一致 */
.source-tag {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: 6px;
}

.metric-value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* ===== 指标数值颜色（val-* 令牌） ===== */
.val-high {
  color: var(--temp-high-ink);
}

.val-low {
  color: var(--temp-low-ink);
}

.val-mid {
  color: var(--text-secondary);
}

/* 数据滞后：整行降透明度 + 数值划线 */
:deep(.el-table__row.is-stale) {
  opacity: 0.6;
}

.metric-value.stale {
  text-decoration: line-through;
}

.empty-state {
  padding: 40px 0;
  font-size: 14px;
  color: var(--text-tertiary-ink);
  text-align: center;
}
</style>
