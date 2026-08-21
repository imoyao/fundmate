<!--
  CrowdingTable · 行业拥挤度排行表格
  从 temperature/index.vue 拆分（#980），模板与相关样式随组件 scoped 迁移。
  内部复用 utils/temperatureFormat 的 crowdingColorClass / crowdingBarStyle。
-->
<template>
  <section class="crowding-section">
    <SectionHeader title="行业拥挤度排行">
      <template #action>
        <span class="bias-updated">更新：{{ date || "暂无" }}</span>
        <el-tooltip
          v-if="stale"
          content="legulegu 数据源暂不可用，当前为最近一次成功计算的结果或占位提示，非实时数据，仅供参考。"
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
      :default-sort="{ prop: 'data.crowding_pct', order: 'ascending' }"
    >
      <el-table-column prop="item_name" label="行业" min-width="140" sortable>
        <template #default="{ row }">
          <span>{{ row.item_name }}</span>
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
        prop="data.crowding_pct"
        label="拥挤度"
        width="220"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <div class="crowding-cell">
            <span
              class="crowding-value"
              :class="crowdingColorClass(row.data?.crowding_pct)"
            >
              {{
                row.data?.crowding_pct != null
                  ? row.data.crowding_pct.toFixed(1) + "%"
                  : "--"
              }}
            </span>
            <div class="crowding-cell-bar">
              <div class="crowding-cell-track">
                <div
                  class="crowding-cell-fill"
                  :class="crowdingColorClass(row.data?.crowding_pct)"
                  :style="crowdingBarStyle(row.data?.crowding_pct)"
                />
              </div>
            </div>
          </div>
        </template>
      </el-table-column>
      <!-- 成交额占比（历史百分位）：复用拥挤度配色与进度条语义，数据源降级为 null 时显示 -- -->
      <el-table-column
        prop="data.amount_pct_rank"
        label="成交额占比"
        width="220"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <div class="crowding-cell">
            <span
              class="crowding-value"
              :class="crowdingColorClass(row.data?.amount_pct_rank)"
            >
              {{
                row.data?.amount_pct_rank != null
                  ? row.data.amount_pct_rank.toFixed(1) + "%"
                  : "--"
              }}
            </span>
            <div class="crowding-cell-bar">
              <div class="crowding-cell-track">
                <div
                  class="crowding-cell-fill"
                  :class="crowdingColorClass(row.data?.amount_pct_rank)"
                  :style="crowdingBarStyle(row.data?.amount_pct_rank)"
                />
              </div>
            </div>
          </div>
        </template>
      </el-table-column>
      <!-- 换手率（历史百分位）：语义与拥挤度一致，越高越热（红），越低越冷（绿） -->
      <el-table-column
        prop="data.turnover_rank"
        label="换手率"
        width="220"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <div class="crowding-cell">
            <span
              class="crowding-value"
              :class="crowdingColorClass(row.data?.turnover_rank)"
            >
              {{
                row.data?.turnover_rank != null
                  ? row.data.turnover_rank.toFixed(1) + "%"
                  : "--"
              }}
            </span>
            <div class="crowding-cell-bar">
              <div class="crowding-cell-track">
                <div
                  class="crowding-cell-fill"
                  :class="crowdingColorClass(row.data?.turnover_rank)"
                  :style="crowdingBarStyle(row.data?.turnover_rank)"
                />
              </div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        prop="data.multiple"
        label="PB倍数"
        width="110"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <span>{{
            row.data?.multiple != null ? row.data.multiple.toFixed(2) : "--"
          }}</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="data.ind_pb"
        label="行业PB"
        width="110"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <span>{{
            row.data?.ind_pb != null ? row.data.ind_pb.toFixed(2) : "--"
          }}</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="data.mkt_pb"
        label="全A中位PB"
        width="120"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <span>{{
            row.data?.mkt_pb != null ? row.data.mkt_pb.toFixed(2) : "--"
          }}</span>
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="140">
        <template #default="{ row }">
          <span v-if="!row.data?.hist_ok" class="crowding-note-tag"
            >分位待历史积累</span
          >
          <span v-else class="crowding-note">{{ row.data?.note || "" }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="!items.length && !loading" class="empty-state">
      行业拥挤度数据暂不可用（legulegu
      数据源受限，本机运行一次建立历史缓存后自动恢复）。
    </div>
  </section>
</template>

<script setup lang="ts">
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  crowdingBarStyle,
  crowdingColorClass
} from "@/utils/temperatureFormat";

defineOptions({ name: "CrowdingTable" });

withDefaults(
  defineProps<{
    /** 拥挤度条目列表（已过滤整组标灰占位，含 data.crowding_pct / amount_pct_rank / turnover_rank 等字段） */
    items: any[];
    /** 数据更新时间，空串显示「暂无」 */
    date?: string;
    /** 数据是否滞后（legulegu 数据源不可用） */
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
/* ===== 行业拥挤度排行区块（自 temperature/index.vue 迁移） ===== */
.crowding-section {
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

/* ===== 拥挤度单元格（数值 + 进度条） ===== */
.crowding-cell {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: flex-end;
}

.crowding-value {
  min-width: 52px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.crowding-cell-bar {
  flex: 1;
  max-width: 120px;
}

.crowding-cell-track {
  position: relative;
  height: 8px;
  overflow: hidden;
  background: var(--border-default);
  border-radius: 4px;
}

.crowding-cell-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}

.crowding-cell-fill.val-low {
  background: var(--temp-low);
}

.crowding-cell-fill.val-mid {
  background: var(--temp-mid);
}

.crowding-cell-fill.val-high {
  background: var(--temp-high);
}

.crowding-note-tag {
  padding: 2px 8px;
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-soft);
  border-radius: 6px;
}

.crowding-note {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ===== 拥挤度数值颜色（val-* 令牌） ===== */
.val-high {
  color: var(--temp-high);
}

.val-low {
  color: var(--temp-low);
}

.val-mid {
  color: var(--text-secondary);
}
</style>
