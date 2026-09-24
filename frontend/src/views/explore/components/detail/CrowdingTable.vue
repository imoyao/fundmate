<!--
  CrowdingTable · 行业拥挤度排行表格
  从 temperature/index.vue 拆分（#980），模板与相关样式随组件 scoped 迁移。
  内部复用 utils/temperatureFormat 的 crowdingColorClass / crowdingBarStyle。
-->
<template>
  <!-- 非 embedded 时根节点换成 CardBlock：区块外壳统一由 CardBlock 提供（#1547 T3.1） -->
  <component
    :is="embedded ? 'section' : CardBlock"
    :class="
      embedded
        ? 'crowding-section crowding-section--embedded'
        : 'crowding-section'
    "
  >
    <!-- embedded：由父级「行业排行」卡片统一承载标题、视图切换与更新时间 -->
    <SectionHeader v-if="!embedded" title="行业拥挤度排行">
      <template #action>
        <span class="bias-updated">更新：{{ date || "暂无" }}</span>
        <el-tooltip
          v-if="stale"
          content="数据暂未更新，当前为最近一次成功计算的结果或占位提示，非实时数据，仅供参考。"
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
      <!-- 榜单序号：一眼看出排名（表现力优化，参考外部站的榜单感） -->
      <el-table-column type="index" label="#" width="48" align="center" />
      <el-table-column
        prop="item_name"
        :label="nameColumnLabel"
        min-width="110"
        sortable
      >
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
        width="140"
        align="right"
        sortable
      >
        <template #header>
          <el-tooltip
            content="综合拥挤度分位（0-100）：综合成交额占比、换手率、60日线上占比、新高占比、融资买入占比、百万大单等多维度合成的历史分位，越高越拥挤。"
            placement="top"
          >
            <span>拥挤度</span>
          </el-tooltip>
        </template>
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
        width="140"
        align="right"
        sortable
      >
        <template #header>
          <el-tooltip
            content="该行业成交额占比在过去 250 个交易日内的百分位。默认由申万宏源官网单源自算（分母 = 当日 31 个申万一级行业成交额之和）；申万源不可用时回退中证指数官网口径（分母为中证全指），两种口径数值不可直接比较。"
            placement="top"
          >
            <span>成交额占比</span>
          </el-tooltip>
        </template>
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
        width="140"
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
      <!-- 以下四列：左侧为当期值、右侧为历史分位 -->
      <el-table-column
        prop="data.ma60_ratio"
        width="120"
        align="right"
        sortable
      >
        <template #header>
          <el-tooltip
            content="60 日均线上方个股占比（该行业成分股中收盘价在 MA60 之上的比例）。右侧为该值的历史分位。"
            placement="top"
          >
            <span>60线上占比</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <div class="dim-cell">
            <span class="dim-value">{{ fmtPct(row.data?.ma60_ratio) }}</span>
            <span
              class="dim-rank"
              :class="crowdingColorClass(row.data?.ma60_ratio_pct)"
            >
              {{ fmtPct(row.data?.ma60_ratio_pct) }}
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        prop="data.high60_ratio"
        width="120"
        align="right"
        sortable
      >
        <template #header>
          <el-tooltip
            content="60 日新高个股占比（该行业成分股中创 60 日新高的比例）。右侧为该值的历史分位。"
            placement="top"
          >
            <span>新高占比</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <div class="dim-cell">
            <span class="dim-value">{{ fmtPct(row.data?.high60_ratio) }}</span>
            <span
              class="dim-rank"
              :class="crowdingColorClass(row.data?.high60_ratio_pct)"
            >
              {{ fmtPct(row.data?.high60_ratio_pct) }}
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        prop="data.margin_ratio"
        width="130"
        align="right"
        sortable
      >
        <template #header>
          <el-tooltip
            content="融资买入额占该行业成交额比例。右侧为该值的历史分位（融资余额是相对慢变量）。"
            placement="top"
          >
            <span>融资买入占比</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <div class="dim-cell">
            <span class="dim-value">{{ fmtPct(row.data?.margin_ratio) }}</span>
            <span
              class="dim-rank"
              :class="crowdingColorClass(row.data?.margin_ratio_pct)"
            >
              {{ fmtPct(row.data?.margin_ratio_pct) }}
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="data.big_order" width="120" align="right" sortable>
        <template #header>
          <el-tooltip
            content="百万大单净买入额（亿元，正=净买入）。"
            placement="top"
          >
            <span>百万大单</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="bigOrderClass(row.data?.big_order)">
            {{
              row.data?.big_order != null
                ? (row.data.big_order > 0 ? "+" : "") +
                  row.data.big_order.toFixed(1) +
                  "亿"
                : "--"
            }}
          </span>
        </template>
      </el-table-column>
      <!-- 行业乖离率 BIASn（简单 MA 口径，#1431）：正=偏离均线上方、负=下方。
           与「行业乖离度排行」表的 LOGBIAS（对数 EMA20）口径不同，故分列展示、互不混淆 -->
      <el-table-column
        v-for="n in BIAS_WINDOWS"
        :key="`bias${n}`"
        :prop="`data.bias${n}`"
        :label="`乖离${n}日`"
        width="76"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <span :class="biasColorClass(row.data?.[`bias${n}`])">
            {{
              row.data?.[`bias${n}`] != null
                ? formatValue(row.data[`bias${n}`]) + "%"
                : "--"
            }}
          </span>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="!items.length && !loading" class="empty-state">
      暂无数据，稍后自动恢复；不影响页面其它部分。
    </div>
  </component>
</template>

<script setup lang="ts">
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  biasColorClass,
  crowdingBarStyle,
  crowdingColorClass,
  formatValue
} from "@/utils/temperatureFormat";

defineOptions({ name: "CrowdingTable" });

/** 百分比展示：null/undefined → “--”，否则一位小数 + %（外部源与自算值共用） */
const fmtPct = (v: number | null | undefined) =>
  v == null ? "--" : `${Number(v).toFixed(1)}%`;

/** 百万大单着色：净买入红、净卖出绿（沿用全站涨跌配色语义） */
const bigOrderClass = (v: number | null | undefined) => {
  if (v == null || v === 0) return "";
  return v > 0 ? "big-order--in" : "big-order--out";
};

/** 行业乖离率窗口（简单 MA 口径，与后端 sw_industry_source.BIAS_WINDOWS 对齐） */
const BIAS_WINDOWS = [6, 20, 60];

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
    /** 嵌入式模式：不渲染自身卡片外壳与标题（由父级「行业排行」卡片承载，用于双视图切换） */
    embedded?: boolean;
    /** 首列名称：行业视图为「行业」、赛道视图为「赛道」 */
    nameColumnLabel?: string;
  }>(),
  {
    date: "",
    stale: false,
    loading: false,
    embedded: false,
    nameColumnLabel: "行业"
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
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-raised);
}

.bias-updated {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

/* embedded：外壳与标题交给父级卡片，本组件只出表格 */
.crowding-section--embedded {
  margin: 0;
}

.bias-stale-pill {
  padding: 2px 8px;
  margin-left: 8px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--color-warning-ink);
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
  color: var(--text-tertiary-ink);
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
  max-width: 96px;
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

/* ===== 外部源维度单元格（当期值 + 历史分位，分位沿用 val-* 档位配色） ===== */
.dim-cell {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: flex-end;
}

.dim-value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.dim-rank {
  min-width: 42px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.dim-rank.val-low {
  color: var(--temp-low-ink);
}

.dim-rank.val-mid {
  color: var(--temp-mid-ink);
}

.dim-rank.val-high {
  color: var(--temp-high-ink);
}

/* 百万大单：净买入（红）/ 净卖出（绿），沿用涨跌配色语义 */
.big-order--in {
  font-variant-numeric: tabular-nums;
  color: var(--temp-high-ink);
}

.big-order--out {
  font-variant-numeric: tabular-nums;
  color: var(--temp-low-ink);
}

/* ===== 拥挤度数值颜色（val-* 令牌） ===== */
.val-high {
  color: var(--temp-high-ink);
}

.val-low {
  color: var(--temp-low-ink);
}

.val-mid {
  color: var(--text-secondary);
}
</style>
