<template>
  <button
    type="button"
    class="fund-link"
    :title="row.fund_name ? row.fund_code : undefined"
    @click="emit('open', row.fund_code)"
  >
    <span class="fund-link__name">
      {{ row.fund_name || row.fund_code }}
      <!-- 持仓体检定位的锚点：榜上哪只是「我的」 -->
      <span v-if="row.in_holdings" class="fund-tag fund-tag--holding"
        >持仓</span
      >
      <span v-else-if="row.in_watchlist" class="fund-tag fund-tag--watch"
        >自选</span
      >
    </span>
    <!-- 名称与代码都显示：跳详情、复核数据都要代码；
                           funds 资料缺失时名称回退代码，此时不重复显示两遍 -->
    <span v-if="row.fund_name" class="fund-link__code">{{
      row.fund_code
    }}</span>
  </button>
</template>

<script setup lang="ts">
// 榜单「基金」单元格（#980 拆分自 index.vue）：名称主显示、代码次要小字、
// 持仓 / 自选徽章。整块可点击跳详情；名称缺失时回退代码且不重复显示两遍。
//
// 只有 props + 一个 emit，不知道榜单、排序、口径——换榜单形态时可单独复用。
import type { FundRiskRankingRow } from "@/api/products";

defineProps<{
  row: FundRiskRankingRow;
}>();
const emit = defineEmits<{
  /** 点整块 → 父层跳详情 */
  open: [code: string];
}>();
</script>

<style scoped>
/* 基金列：名称主显示、代码次要小字（只显 6 位代码用户认不出产品，2026-10-17）。
   整块可点击跳详情；名称缺失时回退代码，此时不重复显示。 */
.fund-link {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-start;
  max-width: 100%;
  overflow: hidden;
  text-align: left;
  cursor: pointer;
  background: none;
  border: none;

  &:hover .fund-link__name {
    color: var(--brand-700);
    text-decoration: underline;
  }

  &__name {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--text-label);
    color: var(--text-primary);
    white-space: nowrap;
  }

  &__code {
    font-size: var(--text-label);
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary-ink);
  }
}

/* 持仓 / 自选徽章：软按钮档（design.md Badge），不用涨跌色——
   标记的是「这是你的」，不是盈亏语义。 */
.fund-tag {
  flex-shrink: 0;
  padding: 0 6px;
  font-size: var(--text-label);
  line-height: 16px;
  border-radius: var(--radius-pill);

  &--holding {
    color: var(--brand-700);
    background: var(--brand-100);
  }

  &--watch {
    color: var(--text-secondary);
    background: var(--bg-soft);
  }
}
</style>
