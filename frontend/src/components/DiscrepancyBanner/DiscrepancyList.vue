<!--
  DiscrepancyList · 差异化明细行（#980 批 B8 从 `DiscrepancyBanner/index.vue` 抽出）

  每条一行：标的代码 → 差异类型 + 差额 → 已挂多久。

  单独成组件的理由不是行数（这一块只有十几行模板），而是**三处「缺数据怎么说」
  都挤在这一行里**，而它们各自的口径不同：
  - `diff !== null` 才显示差额 → 缺差额时整段省略，而不是显示「差额 ¥0」；
  - 差异类型走后端枚举的中文映射（`discrepancyTypeLabel`），未知枚举原样返回；
  - 「已挂多久」按 `now` 这个**取数时刻**算，不是渲染时刻（跨零点会算出不一致的天数）。
-->
<template>
  <ul class="recon-banner__list">
    <li v-for="item in items" :key="item.id" class="recon-banner__item">
      <span class="recon-banner__symbol">{{ item.symbol }}</span>
      <span class="recon-banner__meta">
        {{ discrepancyTypeLabel(item.discrepancy_type) }}差异
        <template v-if="item.diff !== null">
          · 差额 {{ formatDiff(item.diff) }}</template
        >
      </span>
      <span class="recon-banner__age">
        {{ ageLabel(pendingDays(item.first_detected_at, now)) }}
      </span>
    </li>
  </ul>
</template>

<script setup lang="ts">
import type { DiscrepancyItem } from "@/api/reconciliation";
import { discrepancyTypeLabel } from "@/constants";
import { formatDiff } from "@/views/asset/investment/reconcile-workbench/utils/discFormat";
import { ageLabel, pendingDays } from "./helpers";

defineOptions({ name: "DiscrepancyList" });

defineProps<{
  items: DiscrepancyItem[];
  /** 计算「已挂多久」的基准时刻（取数那一刻，不是渲染时刻） */
  now: Date;
}>();
</script>

<style scoped>
.recon-banner__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.recon-banner__item {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  font-size: var(--text-label, 13px);
  color: var(--text-secondary);
}

.recon-banner__symbol {
  font-weight: 600;
  color: var(--text-primary);
}

.recon-banner__meta,
.recon-banner__age {
  color: var(--text-tertiary-ink);
}
</style>
