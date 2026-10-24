<template>
  <!-- 对应净值：净值是基金买入/赎回到账的核心依据，信息层级与重要性匹配。
       原 BuyerForm / SellForm 两份逐字相同的块（#980 收口）。 -->
  <div
    class="text-sm flex items-center gap-2 mt-2 pl-[90px]"
    style="color: var(--text-secondary)"
  >
    <span>对应净值</span>
    <span class="font-semibold" style="color: var(--text-primary)">
      {{ priceText }}
    </span>
    <span class="text-xs" style="color: var(--text-tertiary-ink)">
      · {{ navDateText }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  /** 已回填的净值；未拿到时显示 "--" */
  price?: number;
  /** 净值对应日期（actualNavDate，15:00 后下单顺延一天） */
  navDate?: string;
  /** navDate 缺失时的回退日期（交易日期） */
  fallbackDate?: string;
}>();

const priceText = computed(() =>
  props.price !== undefined && props.price > 0 ? props.price.toFixed(4) : "--"
);
const navDateText = computed(() => props.navDate || props.fallbackDate || "--");
</script>
