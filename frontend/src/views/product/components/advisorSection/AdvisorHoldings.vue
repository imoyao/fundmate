<script setup lang="ts">
import type { AdvisorHoldingsResult } from "@/api/funds";
import { productRoute } from "@/utils/productIdentity";
import { DASH } from "./advisorModel";

/**
 * 成分基金（#980 拆分）。
 *
 * 复用已上线的 holdings 端点，不重写取数链路。**已收录本地名录的才给跳转**：
 * `in_local_db` 为假时说明本地没有这只基金的详情页，给了链接就是死链。
 */
defineProps<{
  holdings: AdvisorHoldingsResult;
}>();
</script>

<template>
  <div v-if="holdings.holdings.length" class="advisor-section__block">
    <h4 class="advisor-section__metrics-title">
      成分基金（{{ holdings.holdings.length }}）
      <span v-if="holdings.as_of_date" class="advisor-section__sub">
        快照 {{ holdings.as_of_date }}
      </span>
    </h4>
    <ul class="advisor-section__holdings">
      <li
        v-for="h in holdings.holdings"
        :key="h.fund_code"
        class="advisor-section__holding"
      >
        <RouterLink
          v-if="h.in_local_db"
          :to="productRoute({ assetType: 'fund', symbol: h.fund_code })"
          class="advisor-section__holding-name advisor-section__holding-name--link"
        >
          {{ h.fund_name || h.fund_code }}
        </RouterLink>
        <span v-else class="advisor-section__holding-name">
          {{ h.fund_name || h.fund_code }}
        </span>
        <span class="advisor-section__holding-ratio">
          {{ h.after_ratio != null ? `${h.after_ratio.toFixed(2)}%` : DASH }}
        </span>
      </li>
    </ul>
  </div>
</template>

<style lang="scss" scoped>
@use "./advisor-base";

.advisor-section__block {
  margin-top: var(--space-3);
}

.advisor-section__holdings {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-2) var(--space-6);
  padding: 0;
  margin: 0;
  list-style: none;
}

.advisor-section__holding {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  min-width: 0;
}

.advisor-section__holding-name {
  font-size: var(--text-label);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.advisor-section__holding-name--link {
  text-decoration: none;
}

.advisor-section__holding-name--link:hover {
  text-decoration: underline;
}

.advisor-section__holding-ratio {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}
</style>
