<!--
  MarketFooter · 探市 / 温度计 页脚（复用）
  图例 + 数据来源 + 免责声明 + 版权
  props:
    - sources: 数据来源 [{ label, url?, dev? }]（dev 表示「开发中」）
    - copyright: 版权文案
    - legend: 可选的图例 [{ label, tone: 'low'|'mid'|'high' }]
-->
<template>
  <footer class="market-footer">
    <div class="market-footer__inner">
      <div v-if="legend && legend.length" class="market-footer__legend">
        <span
          v-for="item in legend"
          :key="item.label"
          class="legend-item"
        >
          <span
            class="legend-dot"
            :class="`legend-dot--${item.tone}`"
          ></span
          >{{ item.label }}
        </span>
      </div>

      <div class="market-footer__sources">
        <span class="market-footer__label">数据来源：</span>
        <template v-for="s in sources" :key="`link-${s.label}`">
          <a
            v-if="!s.dev && s.url"
            class="market-footer__source"
            :href="s.url"
            target="_blank"
            rel="noopener"
            >{{ s.label }}</a
          >
        </template>
        <template v-for="s in sources" :key="`static-${s.label}`">
          <span
            v-if="!s.dev && !s.url"
            class="market-footer__source market-footer__source--static"
            >{{ s.label }}</span
          >
        </template>
        <template v-for="s in sources" :key="`dev-${s.label}`">
          <span
            v-if="s.dev"
            class="market-footer__source market-footer__source--dev"
            >{{ s.label }}</span
          >
        </template>
      </div>

      <div class="market-footer__disclaimer">
        <span class="market-footer__disclaimer-text"
          >市场数据仅供参考，不构成投资建议。</span
        >
      </div>
      <div class="market-footer__copyright">{{ copyright }}</div>
    </div>
  </footer>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    sources: Array<{ label: string; url?: string; dev?: boolean }>;
    copyright?: string;
    legend?: Array<{ label: string; tone: "low" | "mid" | "high" }>;
  }>(),
  {
    copyright: "© 2026 多倍贝 · 让投资更从容",
    legend: () => [
      { label: "偏低（机会）", tone: "low" },
      { label: "适中", tone: "mid" },
      { label: "偏高（谨慎）", tone: "high" }
    ]
  }
);
</script>

<style lang="scss" scoped>
.market-footer {
  background: var(--bg-page);
  border-top: 1px solid var(--border-light);
  color: var(--text-tertiary);

  &__inner {
    max-width: 1400px;
    margin: 0 auto;
    padding: 24px var(--space-12);
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  &__legend {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    font-size: 12px;
    color: var(--text-secondary);

    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .legend-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;

      &--low {
        background: var(--temp-low);
      }
      &--mid {
        background: var(--temp-mid);
      }
      &--high {
        background: var(--temp-high);
      }
    }
  }

  &__sources {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }

  &__label {
    color: var(--text-tertiary);
  }

  &__source {
    color: var(--brand-700);
    text-decoration: none;

    &--static {
      color: var(--text-tertiary);
    }
    &--dev {
      color: var(--text-disabled);
    }
  }

  &__disclaimer {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  &__copyright {
    font-size: 12px;
    color: var(--text-tertiary);
  }
}
</style>
