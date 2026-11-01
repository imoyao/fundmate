<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import DrawerSection from "@/components/ProductDrawer/DrawerSection.vue";
import type { WatchlistItem } from "@/api/watchlist";

/**
 * 「持有」区块：份额/数量 · 市值 · 成本价 · 收益（沿用原 `.wqv-cell` 类名与文案）。
 *
 * 结构换成抽屉共用骨架（`.pd-facts` 两列、单元无边框无底色），`.wqv-cell` 只作为
 * 既有 e2e 的定位钩子保留——它不是样式来源，别在这里加样式。
 */
defineProps<{
  item: WatchlistItem | null;
  precision: number;
}>();

/**
 * 数量带千分位：原实现直接插原始值（`82863.18`），与持仓明细抽屉的
 * `16,000` 两种写法并存。份额是会被逐位核对的数据，位数必须一眼可数。
 * 不加固定小数位——基金份额本身带两位，股票数量是整数，强补两位反而失真。
 */
function quantityText(value: number | null | undefined): string {
  return value == null ? "—" : Number(value).toLocaleString();
}
</script>

<template>
  <DrawerSection title="持有">
    <dl class="pd-facts">
      <div class="pd-fact wqv-cell">
        <dt class="pd-fact__label">持有数量</dt>
        <dd class="pd-fact__value">
          {{ quantityText(item?.holding_quantity) }}
        </dd>
      </div>
      <div class="pd-fact wqv-cell">
        <dt class="pd-fact__label">持仓市值</dt>
        <dd class="pd-fact__value">
          <MoneyDisplay
            v-if="item?.position_market_value != null"
            :value="item.position_market_value"
            size="sm"
            :show-sign="false"
            :auto-color="false"
          />
          <span v-else>—</span>
        </dd>
      </div>
      <div class="pd-fact wqv-cell">
        <dt class="pd-fact__label">成本价</dt>
        <dd class="pd-fact__value">
          <MoneyDisplay
            v-if="item?.holding_cost_price != null"
            :value="item.holding_cost_price"
            :precision="precision"
            size="sm"
            :show-sign="false"
            :auto-color="false"
          />
          <span v-else>—</span>
        </dd>
      </div>
      <div class="pd-fact wqv-cell">
        <dt class="pd-fact__label">持仓收益</dt>
        <dd class="pd-fact__value">
          <MoneyDisplay
            v-if="item?.holding_pnl != null"
            :value="item.holding_pnl"
            size="sm"
          />
          <span v-else>—</span>
        </dd>
      </div>
    </dl>
  </DrawerSection>
</template>
