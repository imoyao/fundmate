<!--
  ExploreWatchlistCards · 观察列表的移动端卡片降级（#821 P2-7，#808 §7.2）
  从 ExploreWatchlistTable 抽出（#980 批 B5，纯搬运）：≤768px 时横向表格不可用，
  改为纵向卡片；信息与桌面列一一对应，涨红跌绿走 RiseFallText 语义变量。

  为什么用 v-else 而不是 CSS 隐藏表格：`el-table` 在窄屏下会把列挤成横向滚动条，
  而卡片要的是**另一套排版**（两列网格），只是把它 display:none 掉并不会让表格
  停止渲染几十行 DOM，移动端首屏成本翻倍。
-->
<template>
  <div v-loading="loading" class="holding-cards">
    <div v-if="!rows.length" class="cards-empty">
      暂无观察资产，添加你关注的标的开始研究
    </div>
    <div v-for="row in rows" :key="row.id ?? row.symbol" class="holding-card">
      <div class="card-head">
        <ProductDisplay
          :name="row.name"
          :symbol="row.symbol"
          :type-label="getTypeLabel(row.type)"
        />
        <div class="card-actions">
          <el-button
            link
            size="small"
            type="primary"
            @click="emit('favorite', row as ExploreRow)"
            >收藏</el-button
          >
          <el-button
            link
            size="small"
            style="color: var(--text-tertiary-ink)"
            @click="emit('remove', row.id)"
            >删除</el-button
          >
        </div>
      </div>

      <div class="card-metrics">
        <div class="metric">
          <span class="metric-label">最新价</span>
          <MoneyDisplay
            :value="row.price"
            :show-sign="false"
            :precision="pricePrecision(row.type)"
          />
        </div>
        <div class="metric">
          <span class="metric-label">涨跌幅</span>
          <RiseFallText :value="row.changePct" />
        </div>
        <template v-if="!isPureObservationMode">
          <div class="metric">
            <span class="metric-label">当日盈亏</span>
            <MoneyDisplay :value="row.pnl ?? 0" :show-sign="true" />
          </div>
          <div class="metric">
            <span class="metric-label">持仓收益</span>
            <MoneyDisplay :value="row.positionPnl ?? 0" :show-sign="true" />
          </div>
        </template>
      </div>

      <div class="card-foot">
        <ExploreAnalysisDropdown
          :type="row.type"
          @command="
            (command: string) => emit('jump', row as ExploreRow, command)
          "
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import ExploreAnalysisDropdown from "./ExploreAnalysisDropdown.vue";
import { getTypeLabel } from "@/constants/assetType";
import { pricePrecision } from "@/utils/pricePrecision";

defineOptions({ name: "ExploreWatchlistCards" });

interface ExploreRow {
  symbol: string;
  type: string;
  name: string;
  id?: string | number;
}

defineProps<{
  rows: any[];
  loading: boolean;
  /** true = 未填成本份额的纯观察模式（隐藏两个盈亏指标） */
  isPureObservationMode: boolean;
}>();

const emit = defineEmits<{
  remove: [id: string];
  jump: [row: ExploreRow, command: string];
  favorite: [row: ExploreRow];
}>();
</script>

<style lang="scss" scoped>
/* ============================================================
   移动端卡片降级（#821 P2-7，≤768px）：仅移动端渲染，桌面端不出现
   ============================================================ */
.holding-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 移动端列表项卡片（非区块卡，故不走 CardBlock）：外观 token 化，禁字面量圆角（#1547 T3.1） */
.cards-empty {
  padding: 32px 16px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-card);
}

.holding-card {
  padding: 14px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-raised);
}

.card-head {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;

  .card-actions {
    display: flex;
    flex-shrink: 0;
  }
}

.card-metrics {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 16px;
  padding-top: 10px;
  margin-top: 10px;
  border-top: 1px solid var(--border-light);

  .metric {
    display: flex;
    gap: 8px;
    align-items: baseline;
    justify-content: space-between;
    font-size: var(--text-small);
  }

  .metric-label {
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }
}

.card-foot {
  padding-top: 10px;
  margin-top: 10px;
  border-top: 1px solid var(--border-light);
}
</style>
