<script setup lang="ts">
// ⚡ 异动解读（§6.1 区块底部）：列出当日命中双线规则的资产 + 规则自述。
// 规则自述的参数取自命中项本身（后端同一次计算下发，展示上保持一致）。
import { Icon as IconifyIconOffline } from "@iconify/vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import type { AnomalyAsset } from "./assetOverviewModel";

defineProps<{
  /** 已按 groups 顺序拍平的命中项，非空才会渲染本面板 */
  items: AnomalyAsset[];
}>();
</script>

<template>
  <div class="anomaly-panel">
    <div class="anomaly-panel__head">
      <IconifyIconOffline icon="ep:lightning" class="anomaly-panel__icon" />
      <span>异动解读</span>
      <span class="anomaly-panel__count">{{ items.length }} 项</span>
    </div>
    <ul class="anomaly-panel__list">
      <li v-for="item in items" :key="item.asset.key" class="anomaly-item">
        <span class="anomaly-item__name">{{ item.asset.name }}</span>
        <span class="anomaly-item__change">
          <RiseFallText
            :value="item.anomaly.today_pct"
            :precision="2"
            size="sm"
          />
        </span>
        <span class="anomaly-item__note">{{ item.anomaly.basis_note }}</span>
      </li>
    </ul>
    <div class="anomaly-panel__foot">
      判定用「双线规则」：单日涨跌超过自身近
      {{ items[0].anomaly.sigma_window }} 个交易日波动（σ）的
      {{ items[0].anomaly.sigma_multiple }} 倍，或超过
      {{ items[0].anomaly.abs_threshold }}%
      绝对阈值。此处为规则自述，暂未接入新闻源。
    </div>
  </div>
</template>

<style lang="scss" scoped>
.anomaly-panel {
  padding: 14px 16px;
  background: var(--color-warning-20);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-md);

  &__head {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 10px;
    font-size: var(--text-small);
    font-weight: 600;
    color: var(--text-primary);
  }

  &__icon {
    font-size: var(--text-body);
    color: var(--brand-700);
  }

  &__count {
    font-size: var(--text-label);
    font-weight: 400;
    color: var(--text-secondary);
  }

  &__list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 0;
    margin: 0;
    list-style: none;
  }

  &__foot {
    padding-top: 10px;
    margin-top: 10px;
    font-size: var(--text-label);
    line-height: 1.6;
    color: var(--text-secondary);
    border-top: 1px solid var(--color-warning);
  }
}

.anomaly-item {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
  font-size: var(--text-label);

  &__name {
    min-width: 72px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__change {
    font-variant-numeric: tabular-nums;
  }

  &__note {
    flex: 1 1 240px;
    line-height: 1.6;
    color: var(--text-secondary);
  }
}
</style>
