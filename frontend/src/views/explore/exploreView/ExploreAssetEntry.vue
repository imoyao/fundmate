<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { ASSET_CATEGORIES, ASSET_CATEGORY_TOKEN } from "@/constants/market";

/**
 * 大类资产观察入口（#1671 方案 b，2026-10 拆分自 views/explore/index.vue）。
 *
 * 区块本体在「深度」档，概览档只留这一行轻量入口：既让概览档聚焦
 * （温度锚点 + 观察列表），又不丢这个能力的发现性。
 * 点击后切档 + 滚动定位 + 以展开态渲染，都是页面的编排职责，组件只抛事件。
 */
const emit = defineEmits<{ (e: "open"): void }>();
</script>

<template>
  <section class="asset-entry">
    <div class="asset-entry__inner">
      <div class="asset-entry__text">
        <div class="asset-entry__title">大类资产观察</div>
        <div class="asset-entry__cats">
          <span
            v-for="cat in ASSET_CATEGORIES"
            :key="cat"
            class="asset-entry__cat"
          >
            <i
              class="asset-entry__dot"
              :style="{ background: ASSET_CATEGORY_TOKEN[cat] }"
            />{{ cat }}
          </span>
        </div>
      </div>
      <button type="button" class="asset-entry__btn" @click="emit('open')">
        去深度档查看
        <IconifyIconOffline icon="ep:arrow-right" />
      </button>
    </div>
  </section>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* ============================================================
   大类资产观察入口（#1671 方案 b）
   区块本体已移入深度档，此处只做一行轻量引导；样式对齐转化区的卡片，
   分类圆点直接复用 --asset-cat-* 令牌，与深度档区块同貌。
   ============================================================ */
.asset-entry {
  max-width: var(--layout-content-width);
  padding: 0 24px 16px;
  margin: 0 auto;

  &__inner {
    display: flex;
    gap: 20px;
    align-items: center;
    justify-content: space-between;
    padding: 14px 24px;
    background: var(--bg-card);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-card);
    box-shadow: var(--shadow-raised);
  }

  &__title {
    font-size: var(--text-body);
    font-weight: 600;
    color: var(--text-primary);
  }

  &__cats {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 6px;
  }

  &__cat {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    font-size: var(--text-label);
    color: var(--text-secondary);
  }

  &__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  &__btn {
    display: inline-flex;
    flex-shrink: 0;
    gap: 4px;
    align-items: center;
    height: 32px;
    padding: 0 14px;
    font-family: inherit;
    font-size: var(--text-label);
    color: var(--brand-700);
    cursor: pointer;
    background: var(--brand-100);
    border: 1px solid var(--brand-400);
    border-radius: var(--radius-pill);
    transition: background-color 150ms ease;

    &:hover {
      background: var(--brand-200);
    }

    &:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
    }
  }
}

@include bp.below("md") {
  .asset-entry {
    padding: 0 16px 16px;

    &__inner {
      flex-direction: column;
      gap: 12px;
      align-items: stretch;
    }
  }
}
</style>
