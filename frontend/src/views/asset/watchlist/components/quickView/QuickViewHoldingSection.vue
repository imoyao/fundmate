<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import type { WatchlistItem } from "@/api/watchlist";

defineProps<{
  item: WatchlistItem;
  precision: number;
}>();
</script>

<template>
  <!-- 持有（仅可持有品类） -->
  <section class="wqv-sec">
    <h4 class="wqv-sec__title">持有</h4>
    <dl class="wqv-grid">
      <div class="wqv-cell">
        <dt class="wqv-label">持有数量</dt>
        <dd class="wqv-value">
          {{ item.holding_quantity != null ? item.holding_quantity : "—" }}
        </dd>
      </div>
      <div class="wqv-cell">
        <dt class="wqv-label">持仓市值</dt>
        <dd class="wqv-value">
          <MoneyDisplay
            v-if="item.position_market_value != null"
            :value="item.position_market_value"
            size="sm"
          />
          <span v-else class="wqv-empty">—</span>
        </dd>
      </div>
      <div class="wqv-cell">
        <dt class="wqv-label">成本价</dt>
        <dd class="wqv-value">
          <MoneyDisplay
            v-if="item.holding_cost_price != null"
            :value="item.holding_cost_price"
            :precision="precision"
            size="sm"
          />
          <span v-else class="wqv-empty">—</span>
        </dd>
      </div>
      <div class="wqv-cell">
        <dt class="wqv-label">持仓收益</dt>
        <dd class="wqv-value">
          <MoneyDisplay
            v-if="item.holding_pnl != null"
            :value="item.holding_pnl"
            size="sm"
          />
          <span v-else class="wqv-empty">—</span>
        </dd>
      </div>
    </dl>
  </section>
</template>

<style scoped lang="scss">
@use "./wqv-base";
</style>
