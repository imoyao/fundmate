<script setup lang="ts">
// 单资产卡片（数据驱动，页面上最多 20 张）。
// 四种形态都由 asset 字段决定：软占位（available=false）/ 有相对位置 / 无相对位置 / 带口径。
import { Icon as IconifyIconOffline } from "@iconify/vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import type { MarketAsset } from "@/api/market";
import { positionColor, positionLabelColor } from "./assetOverviewModel";

defineProps<{ asset: MarketAsset }>();
</script>

<template>
  <div class="asset-card" :class="{ 'asset-card--disabled': !asset.available }">
    <div class="asset-card__top">
      <span class="asset-card__name">
        {{ asset.name }}
        <!-- ⚡ 异动标记（§5.5 双线规则），命中才渲染；用图标而非 emoji（AGENTS.md 禁 emoji） -->
        <span
          v-if="asset.anomaly"
          class="asset-card__anomaly"
          :title="`异动：${asset.anomaly.basis_note}`"
        >
          <IconifyIconOffline icon="ep:lightning" />
        </span>
      </span>
      <span
        v-if="asset.caliber"
        class="asset-card__caliber"
        :title="asset.caliber"
        >口径</span
      >
    </div>

    <!-- 软占位：置灰 + — + 原因 -->
    <template v-if="!asset.available">
      <div class="asset-card__change asset-card__change--na">—</div>
      <div class="asset-card__reason">{{ asset.reason }}</div>
    </template>

    <!-- 可取数 -->
    <template v-else>
      <div class="asset-card__change">
        <RiseFallText :value="asset.change_pct ?? 0" :precision="2" size="lg" />
      </div>

      <!-- 相对位置条（温度三色 + 游标） -->
      <div
        v-if="asset.position"
        class="pos-bar"
        :title="`${asset.position.basis} · 近${asset.position.window}日分位 ${asset.position.percentile}%`"
      >
        <div class="pos-bar__track">
          <div
            class="pos-bar__cursor"
            :style="{
              left: asset.position.percentile + '%',
              background: positionColor(asset)
            }"
          />
        </div>
        <div class="pos-bar__meta">
          <span class="pos-bar__basis">{{ asset.position.basis }}</span>
          <span
            class="pos-bar__label"
            :style="{ color: positionLabelColor(asset) }"
            >{{ asset.position.label }}</span
          >
        </div>
      </div>
      <div v-else class="asset-card__nopin">—</div>

      <div v-if="asset.caliber" class="asset-card__caliber-text">
        {{ asset.caliber }}
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.asset-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0; /* 允许在窄轨道内收窄，防「内容 min-content 顶宽 → 横向溢出」（#1549 T4.3） */
  padding: 14px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-raised);

  &--disabled {
    background: var(--bg-soft);
    border-style: dashed;
    box-shadow: none;
  }

  &__top {
    display: flex;
    gap: 6px;
    align-items: center;
    justify-content: space-between;
  }

  &__name {
    min-width: 0; /* 长名称换行而非顶宽（禁截断，故不加 ellipsis） */
    font-size: var(--text-small);
    font-weight: 600;
    color: var(--text-primary);
  }

  /* ⚡ 异动标记：暖沙金底 + 品牌橙图标，刻意避开涨跌红绿语义 */
  &__anomaly {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0 3px;
    margin-left: 4px;
    font-size: var(--text-label);
    line-height: 1.5;
    vertical-align: middle;
    color: var(--brand-700);
    cursor: help;
    background: var(--color-warning-20);
    border-radius: 4px;
  }

  &__caliber {
    flex-shrink: 0;
    padding: 1px 6px;
    font-size: var(--text-label);
    color: var(--text-secondary);
    cursor: help;
    background: var(--bg-soft);
    border-radius: 4px;
  }

  &__change {
    font-variant-numeric: tabular-nums;

    /* 无数据占位「—」：原文案用 --text-disabled（1.67:1）在卡底近乎不可见，
       用户无法区分「无数据」与「渲染坏了」。占位符是信息，不是禁用控件，
       不适用 WCAG 对 inactive component 的豁免，故改用文字级令牌（5.78:1）。 */
    &--na {
      font-family: var(--font-mono);
      font-size: var(--text-display);
      font-weight: 700;
      color: var(--text-tertiary-ink);
    }
  }

  /* 不可用原因说明：真实可读文案，13px 正文级 → 必须 ≥ 4.5:1 */
  &__reason {
    font-size: var(--text-label);
    line-height: 1.5;
    color: var(--text-tertiary-ink);
  }

  /* 同 &--na：占位「—」 */
  &__nopin {
    font-family: var(--font-mono);
    font-size: var(--text-num-strong);
    color: var(--text-tertiary-ink);
  }

  &__caliber-text {
    font-size: var(--text-label);
    line-height: 1.5;
    color: var(--text-tertiary-ink);
  }
}

/* 相对位置条 */
.pos-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;

  &__track {
    position: relative;
    height: 6px;
    background: linear-gradient(
      90deg,
      var(--temp-low) 0%,
      var(--temp-mid) 50%,
      var(--temp-high) 100%
    );
    border-radius: 3px;
  }

  &__cursor {
    position: absolute;
    top: 50%;
    width: 10px;
    height: 10px;
    border: 2px solid var(--text-inverse);
    border-radius: 50%;
    box-shadow: 0 0 0 1px rgb(0 0 0 / 10%);
    transform: translate(-50%, -50%);
  }

  &__meta {
    display: flex;
    gap: 6px;
    align-items: baseline;
    justify-content: space-between;
  }

  &__basis {
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  &__label {
    font-size: var(--text-label);
    font-weight: 600;
  }
}
</style>
