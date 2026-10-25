<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import type { WatchlistItem } from "@/api/watchlist";
import { hasChangeOf, hasPriceOf } from "./quickViewModel";

const props = defineProps<{
  item: WatchlistItem;
  precision: number;
}>();

const hasPrice = () => hasPriceOf(props.item);
const hasChange = () => hasChangeOf(props.item);
</script>

<template>
  <section class="wqv-sec">
    <h4 class="wqv-sec__title">行情</h4>
    <dl class="wqv-grid">
      <div class="wqv-cell">
        <dt class="wqv-label">最新价</dt>
        <dd class="wqv-value">
          <MoneyDisplay
            v-if="hasPrice()"
            :value="item.current_price as number"
            :precision="precision"
            size="sm"
          />
          <span v-else class="wqv-empty">—</span>
        </dd>
      </div>
      <div class="wqv-cell">
        <dt class="wqv-label">涨跌幅</dt>
        <dd class="wqv-value">
          <RiseFallText
            v-if="hasChange()"
            :value="item.change_pct as number"
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
