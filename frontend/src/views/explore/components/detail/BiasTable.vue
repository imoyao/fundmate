<!--
  BiasTable · 行业乖离度排行表格
  从 temperature/index.vue 拆分（#980），模板与相关样式随组件 scoped 迁移。
  内部复用 utils/temperatureFormat 的 biasColorClass / biasBarStyle / formatValue。
-->
<template>
  <section class="bias-section">
    <SectionHeader title="行业乖离度排行">
      <template #action>
        <span class="bias-updated">更新：{{ date || "暂无" }}</span>
        <el-tooltip
          v-if="stale"
          content="东财行情接口暂不可用，当前乖离率基于最近一次成功抓取的价格计算，非实时数据，仅供参考。"
          placement="top"
        >
          <span class="bias-stale-pill">数据滞后</span>
        </el-tooltip>
      </template>
    </SectionHeader>
    <el-table
      v-loading="loading"
      :data="items"
      border
      style="width: 100%"
      max-height="520"
      :default-sort="{ prop: 'data.bias', order: 'ascending' }"
    >
      <el-table-column prop="item_name" label="行业" min-width="140" sortable>
        <template #default="{ row }">
          <span>{{ row.item_name || row.name }}</span>
          <el-tag
            v-if="row.stale"
            size="small"
            type="warning"
            effect="plain"
            class="bias-stale-tag"
            >滞后</el-tag
          >
        </template>
      </el-table-column>
      <el-table-column
        prop="data.bias"
        label="乖离率"
        width="130"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <span :class="biasColorClass(row.data?.bias ?? row.logbias)">
            {{ formatValue(row.data?.bias ?? row.logbias) }}%
          </span>
        </template>
      </el-table-column>
      <el-table-column label="偏离度" min-width="200">
        <template #default="{ row }">
          <div class="bias-cell-bar">
            <div class="bias-cell-track">
              <div class="bias-cell-zero" />
              <div
                class="bias-cell-fill"
                :class="biasColorClass(row.data?.bias ?? row.logbias)"
                :style="biasBarStyle(row.data?.bias ?? row.logbias)"
              />
            </div>
            <div class="bias-cell-labels">
              <span>低位区</span>
              <span>高位区</span>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        prop="data.position"
        label="波段位置"
        width="120"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <span>{{
            row.data?.position !== undefined
              ? row.data.position.toFixed(1)
              : "--"
          }}</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="data.label"
        label="信号"
        width="130"
        align="center"
      >
        <template #default="{ row }">
          <el-tag
            :type="
              (row.data?.label || row.label) === '高位区(绿卖)'
                ? 'danger'
                : (row.data?.label || row.label) === '低位区(红买)'
                  ? 'success'
                  : 'info'
            "
            size="small"
            effect="dark"
          >
            {{ row.data?.label || row.label || "中性" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="data.close"
        label="收盘价"
        width="120"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <span>{{ formatValue(row.data?.close ?? row.close) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="!items.length && !loading" class="empty-state">
      暂无乖离率数据
    </div>
  </section>
</template>

<script setup lang="ts">
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  biasBarStyle,
  biasColorClass,
  formatValue
} from "@/utils/temperatureFormat";

defineOptions({ name: "BiasTable" });

withDefaults(
  defineProps<{
    /** 乖离率条目列表（含 data.bias / logbias / data.close 等字段） */
    items: any[];
    /** 数据更新时间，空串显示「暂无」 */
    date?: string;
    /** 数据是否滞后（东财行情接口不可用） */
    stale?: boolean;
    /** 加载中（el-table v-loading） */
    loading?: boolean;
  }>(),
  {
    date: "",
    stale: false,
    loading: false
  }
);
</script>

<style lang="scss" scoped>
/* ===== 乖离度排行区块（自 temperature/index.vue 迁移） ===== */
.bias-section {
  padding: 20px 24px;
  margin-bottom: 24px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.bias-updated {
  font-size: 12px;
  color: var(--text-tertiary);
}

.bias-stale-pill {
  padding: 2px 8px;
  margin-left: 8px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--color-warning, #d97706);
  white-space: nowrap;
  cursor: help;
  background: color-mix(
    in srgb,
    var(--color-warning, #d97706) 12%,
    transparent
  );
  border: 1px solid
    color-mix(in srgb, var(--color-warning, #d97706) 35%, transparent);
  border-radius: 6px 6px 6px 0;
}

.bias-stale-tag {
  margin-left: 6px;
  vertical-align: middle;
}

.empty-state {
  padding: 40px 0;
  font-size: 14px;
  color: var(--text-tertiary);
  text-align: center;
}

/* ===== 乖离率表格单元格内颜色条 ===== */
.bias-cell-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bias-cell-track {
  position: relative;
  height: 8px;
  overflow: hidden;
  background: var(--border-default);
  border-radius: 4px;
}

.bias-cell-zero {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  z-index: 1;
  width: 2px;
  background: var(--text-tertiary);
  transform: translateX(-50%);
}

.bias-cell-fill {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 4px;
  transition:
    width 0.4s ease,
    left 0.4s ease;
}

.bias-cell-fill.bias-low,
.bias-cell-fill.bias-extreme-low {
  background: var(--temp-low);
}

.bias-cell-fill.bias-high,
.bias-cell-fill.bias-extreme-high {
  background: var(--temp-high);
}

.bias-cell-fill.bias-neutral {
  background: var(--temp-mid);
}

.bias-cell-labels {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-tertiary);
}

/* ===== 乖离率数值颜色 ===== */
.bias-extreme-high {
  color: var(--temp-high);
}

.bias-high {
  color: color-mix(in srgb, var(--temp-high) 85%, var(--text-primary));
}

.bias-extreme-low {
  color: var(--temp-low);
}

.bias-low {
  color: color-mix(in srgb, var(--temp-low) 85%, var(--text-primary));
}

.bias-neutral {
  color: var(--text-secondary);
}
</style>
