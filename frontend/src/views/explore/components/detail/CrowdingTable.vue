<!--
  CrowdingTable · 行业拥挤度排行表格
  从 temperature/index.vue 拆分（#980），模板与相关样式随组件 scoped 迁移。
  内部复用 utils/temperatureFormat 的 crowdingColorClass / crowdingBarStyle。

  #980 批 B5 二次拆分（纯搬运，零视觉/行为变更）：
    · 三类单元格（分值+条 / 双数字 / 表头气泡）→ CrowdingMetricCell /
      CrowdingDimCell / CrowdingHeaderTip
    · 数字写法（`--` 占位、正负号、亿单位）→ crowdingCells.ts 纯函数
  本文件只留列定义与外壳。
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
      <!-- 三列同构（回看 CrowdingMetricCell）：拥挤度 / 成交额占比 / 换手率都是
           「历史分位 0–100 + 进度条」，配色语义一致——越高越热（红），越低越冷（绿）。 -->
      <el-table-column
        prop="data.crowding_pct"
        width="140"
        align="right"
        sortable
      >
        <template #header>
          <CrowdingHeaderTip
            content="综合拥挤度分位（0-100）：综合成交额占比、换手率、60日线上占比、新高占比、融资买入占比、百万大单等多维度合成的历史分位，越高越拥挤。"
            >拥挤度</CrowdingHeaderTip
          >
        </template>
        <template #default="{ row }">
          <CrowdingMetricCell :value="row.data?.crowding_pct" />
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
          <CrowdingHeaderTip
            content="该行业成交额占比在过去 250 个交易日内的百分位。默认由申万宏源官网单源自算（分母 = 当日 31 个申万一级行业成交额之和）；申万源不可用时回退中证指数官网口径（分母为中证全指），两种口径数值不可直接比较。"
            >成交额占比</CrowdingHeaderTip
          >
        </template>
        <template #default="{ row }">
          <CrowdingMetricCell :value="row.data?.amount_pct_rank" />
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
          <CrowdingMetricCell :value="row.data?.turnover_rank" />
        </template>
      </el-table-column>
      <!-- 以下四列：左侧为当期值、右侧为历史分位（回看 CrowdingDimCell） -->
      <el-table-column
        prop="data.ma60_ratio"
        width="120"
        align="right"
        sortable
      >
        <template #header>
          <CrowdingHeaderTip
            content="60 日均线上方个股占比（该行业成分股中收盘价在 MA60 之上的比例）。右侧为该值的历史分位。"
            >60线上占比</CrowdingHeaderTip
          >
        </template>
        <template #default="{ row }">
          <CrowdingDimCell
            :value="row.data?.ma60_ratio"
            :rank="row.data?.ma60_ratio_pct"
          />
        </template>
      </el-table-column>
      <el-table-column
        prop="data.high60_ratio"
        width="120"
        align="right"
        sortable
      >
        <template #header>
          <CrowdingHeaderTip
            content="60 日新高个股占比（该行业成分股中创 60 日新高的比例）。右侧为该值的历史分位。"
            >新高占比</CrowdingHeaderTip
          >
        </template>
        <template #default="{ row }">
          <CrowdingDimCell
            :value="row.data?.high60_ratio"
            :rank="row.data?.high60_ratio_pct"
          />
        </template>
      </el-table-column>
      <el-table-column
        prop="data.margin_ratio"
        width="130"
        align="right"
        sortable
      >
        <template #header>
          <CrowdingHeaderTip
            content="融资买入额占该行业成交额比例。右侧为该值的历史分位（融资余额是相对慢变量）。"
            >融资买入占比</CrowdingHeaderTip
          >
        </template>
        <template #default="{ row }">
          <CrowdingDimCell
            :value="row.data?.margin_ratio"
            :rank="row.data?.margin_ratio_pct"
          />
        </template>
      </el-table-column>
      <el-table-column prop="data.big_order" width="120" align="right" sortable>
        <template #header>
          <CrowdingHeaderTip content="百万大单净买入额（亿元，正=净买入）。"
            >百万大单</CrowdingHeaderTip
          >
        </template>
        <template #default="{ row }">
          <span :class="bigOrderClass(row.data?.big_order)">
            {{ bigOrderText(row.data?.big_order) }}
          </span>
        </template>
      </el-table-column>
      <!-- 行业乖离率 BIASn（简单 MA 口径，#1431）：正=偏离均线上方、负=下方。
           与「行业乖离度排行」表的 LOGBIAS（对数 EMA20）口径不同，故分列展示、互不混淆。
           `showBiasColumns` 为 false 时不渲染这三列（见 prop 注释）：赛道分类拿不到 BIASn，
           硬保留就是整列 `--`，用户会读成「数据坏了」，而不是「该维度不适用」。 -->
      <el-table-column
        v-for="n in showBiasColumns ? BIAS_WINDOWS : []"
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
import CrowdingMetricCell from "./CrowdingMetricCell.vue";
import CrowdingDimCell from "./CrowdingDimCell.vue";
import CrowdingHeaderTip from "./CrowdingHeaderTip.vue";
import { biasColorClass, formatValue } from "@/utils/temperatureFormat";
import { BIAS_WINDOWS, bigOrderClass, bigOrderText } from "./crowdingCells";

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
    /** 嵌入式模式：不渲染自身卡片外壳与标题（由父级「行业排行」卡片承载，用于双视图切换） */
    embedded?: boolean;
    /** 首列名称：行业视图为「行业」、赛道视图为「赛道」 */
    nameColumnLabel?: string;
    /**
     * 是否展示行业乖离率三列（乖离6 / 20 / 60 日）。
     * WHY：后端 BIASn 只对 `category='sw'` 补齐（`_merge_sw_bias` 不处理 track，
     * `fundfof_crowding.py` 亦注明「赛道维度无 BIASn，该维度不适用」），赛道记录的 data 里
     * 没有 bias6/20/60 三个键 —— 保留这三列就是整列 `--`，看起来像数据故障。
     * 默认 true：申万行业路径（以及任何未传该 prop 的旧用法）表现零变化。
     * 赛道为何不额外加「不适用」标注：父级标题的 info 已写明该口径，不另造第二套说法。
     */
    showBiasColumns?: boolean;
  }>(),
  {
    date: "",
    stale: false,
    loading: false,
    embedded: false,
    nameColumnLabel: "行业",
    showBiasColumns: true
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
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* embedded：外壳与标题交给父级卡片，本组件只出表格 */
.crowding-section--embedded {
  margin: 0;
}

.bias-stale-pill {
  padding: 2px 8px;
  margin-left: 8px;
  font-size: var(--text-label);
  font-weight: 500;
  line-height: 1.4;
  color: var(--color-warning-ink);
  white-space: nowrap;
  cursor: help;
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 35%, transparent);
  border-radius: 6px 6px 6px 0;
}

.bias-stale-tag {
  margin-left: 6px;
  vertical-align: middle;
}

.empty-state {
  padding: 40px 0;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
  text-align: center;
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

/* ===== 拥挤度数值颜色（val-* 令牌） =====
   这三条是**跨子件共用**的：`CrowdingMetricCell` 的数值与 `CrowdingDimCell` 的分位
   都靠 `*.val-*` 拿颜色。scoped 样式不穿透子组件，所以在父级用 `:deep()` 出**一份**——
   各子件再写一份虽然也能跑，但那意味着同一个令牌值有三处副本，改色必漏。 */
:deep(.val-high) {
  color: var(--temp-high-ink);
}

:deep(.val-low) {
  color: var(--temp-low-ink);
}

:deep(.val-mid) {
  color: var(--text-secondary);
}
</style>
