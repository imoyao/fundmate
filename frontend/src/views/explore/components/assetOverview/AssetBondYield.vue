<script setup lang="ts">
// 债券收益率轨（双轨：价格轨在卡片，收益率轨在此单独展示，不套涨红跌绿）。
import type { BondYield } from "@/api/market";
import { yieldTone } from "./assetOverviewModel";

defineProps<{ bondYield: BondYield }>();
</script>

<template>
  <div class="bond-yield">
    <div class="bond-yield__head">债券收益率轨（双轨对照）</div>
    <div class="bond-yield__items">
      <div class="bond-yield__item">
        <span class="bond-yield__label">中债 10Y</span>
        <span class="bond-yield__val">{{ bondYield.cn_10y }}%</span>
        <span
          class="bond-yield__bp"
          :style="{ color: yieldTone(bondYield.cn_10y_change_bp) }"
          >{{ (bondYield.cn_10y_change_bp ?? 0) >= 0 ? "+" : ""
          }}{{ bondYield.cn_10y_change_bp ?? 0 }} bp</span
        >
      </div>
      <div v-if="bondYield.us_10y != null" class="bond-yield__item">
        <span class="bond-yield__label">美债 10Y</span>
        <span class="bond-yield__val">{{ bondYield.us_10y }}%</span>
        <span
          class="bond-yield__bp"
          :style="{ color: yieldTone(bondYield.us_10y_change_bp) }"
          >{{ (bondYield.us_10y_change_bp ?? 0) >= 0 ? "+" : ""
          }}{{ bondYield.us_10y_change_bp ?? 0 }} bp</span
        >
      </div>
      <span class="bond-yield__hint"
        >收益率上行 ≠ 利好，与价格轨涨跌语义相反</span
      >
    </div>
  </div>
</template>

<style lang="scss" scoped>
.bond-yield {
  padding: 14px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-raised);

  &__head {
    margin-bottom: 10px;
    font-size: var(--text-small);
    font-weight: 600;
    color: var(--text-primary);
  }

  &__items {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    align-items: center;
  }

  &__item {
    display: flex;
    gap: 8px;
    align-items: baseline;
  }

  &__label {
    font-size: var(--text-label);
    color: var(--text-secondary);
  }

  &__val {
    font-family: var(--font-mono);
    font-size: var(--text-num-strong);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
  }

  &__bp {
    font-family: var(--font-mono);
    font-size: var(--text-label);
    font-variant-numeric: tabular-nums;
  }

  &__hint {
    margin-left: auto;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }
}

/* 断点原样搬迁（阈值随样式块从 ExploreAssetOverview.vue 搬来）：`<=768` 与
   `bp.below("md")` 的 `<768` 差 1px，iPad 竖屏恰好落在这个像素上，改写法即改行为。
   breakpoint-allow 原样搬迁的存量阈值 */
@media (width <= 768px) {
  .bond-yield__hint {
    margin-left: 0;
  }
}
</style>
