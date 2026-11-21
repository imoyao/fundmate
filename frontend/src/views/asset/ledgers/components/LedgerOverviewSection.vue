<template>
  <!-- 顶部：净资产卡 + 资产配置环形图卡。xl 起左右分栏（5:3），xl 以下单列堆叠：
       768~1279 若继续两栏，hero 大数字会被压进 1/2 列宽——57px 的
       「¥1,540,962.73」在 500px 内就要换行，宁可让环形图下移一层。 -->
  <div class="overview-grid">
    <NetWorthCard
      :net-worth="p.overviewData.net_worth"
      :total-assets="p.totalAssets"
      :liability-total="p.overviewData.liability_total"
      :liability-rate="p.liabilityRate"
      :show-high-liability-warning="p.showHighLiabilityWarning"
      :last-update="p.lastUpdate"
    />
    <!-- 资产配置环形图卡（#984 拆分至 components/LedgerAllocationCard.vue） -->
    <LedgerAllocationCard
      :groups="p.overviewData?.groups ?? []"
      :total-assets="p.totalAssets"
    />
  </div>

  <!-- 聚合汇总卡：基金 / 股票 两卡并排（窄屏单列堆叠）。整卡可点下钻。
       口径注解（金额与首页「基金」列本就不同集合，别把差异当 bug）：
       · 金额取 `fund/securities-aggregation`，用**库内最新净值 / 收盘价**；
         总资产（`/summary/`）取 `positions.current_price` 的持仓快照价。
         同步滞后时两者差一个净值日，属既有口径差（tech-debt 已登记）。
       · 基金卡市值含货币基金与 E 账户份额，但货基没有统一当日估值口径
         ⇒ 当日收益只来自 fund，标签必须写「不含货基」。 -->
  <div class="aggregation-cards-grid">
    <AggregationSummaryCard
      title="基金"
      hint="含货币基金、E 账户份额"
      :amount="p.fundTotalYuan"
      :pnl="fundTodayPnl"
      pnl-label="当日收益（不含货基）"
      :share="fundShare"
      icon="ep:trend-charts"
      accent="--asset-cat-fund"
      @open="p.goToFundAggregation"
    />
    <AggregationSummaryCard
      title="股票"
      hint="含 ETF、可转债"
      :amount="p.securitiesTotalYuan"
      :pnl="stockTodayPnl"
      pnl-label="当日收益"
      :share="stockShare"
      icon="ep:data-line"
      accent="--asset-cat-stock"
      @open="p.goToSecuritiesAggregation"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive } from "vue";
import NetWorthCard from "./NetWorthCard.vue";
import LedgerAllocationCard from "./LedgerAllocationCard.vue";
import AggregationSummaryCard from "./AggregationSummaryCard.vue";
import { shareOfTotal } from "./overviewShare";
import type { useLedgerList } from "../composables/useLedgerList";

defineOptions({ name: "LedgerOverviewSection" });

/**
 * 账户列表页顶部汇总区（#980 P1-C 结构拆分）：
 * 净资产卡 + 资产配置环形图 + 基金/股票聚合汇总卡。
 * 本文件只留栅格编排，卡片内容各自成组件。
 * page 为 index 注入的状态单体；p 用 reactive 解包，使模板表达式与拆分前逐字一致。
 */
const props = defineProps<{ page: ReturnType<typeof useLedgerList> }>();
const p = reactive(props.page);

// 品类维度的当日收益：一次批量请求已由 useLedgerList 发出，这里只按 key 取。
// 没数（null / 没这个桶）保持 null，模板显示「—」而不是 0。
const fundTodayPnl = computed(() => p.todayPnlByClass.get("fund") ?? null);
const stockTodayPnl = computed(() => p.todayPnlByClass.get("stock") ?? null);

// 品类占全部资产的比重：只做标注，不参与任何计算。不可算时为 null，整项不渲染。
const fundShare = computed(() => shareOfTotal(p.fundTotalYuan, p.totalAssets));
const stockShare = computed(() =>
  shareOfTotal(p.securitiesTotalYuan, p.totalAssets)
);
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.overview-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-compact);
  margin-bottom: var(--space-standard);
}

.aggregation-cards-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-compact);
  margin-bottom: var(--space-loose);
}

/* lg（1024）起两栏等宽：再窄（768~1023）两栏会把 hero 压进 360px 以下，
   而单列在 1024~1279 又会把净资产卡拉到 780px 宽、右侧空出 400px（实测）。
   等宽 + hero 缩到 40px（见 NetWorthCard）是这一档的最优解。 */
@include bp.above("lg") {
  .overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .aggregation-cards-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* xl（1280）起净资产卡略宽（1.2 : 1）：此时内容区足够，hero 恢复 57px，
   环形图也让得出一行图例的空间。 */
@include bp.above("xl") {
  .overview-grid {
    grid-template-columns: minmax(0, 1.2fr) minmax(320px, 1fr);
  }
}
</style>
