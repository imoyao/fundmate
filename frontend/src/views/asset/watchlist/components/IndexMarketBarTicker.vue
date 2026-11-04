<!--
  IndexMarketBarTicker · 大盘指数条「折叠态」单行跑马灯（#watchlist）

  为什么是跑马灯而不是横向滚动条：
    折叠态的用途是「扫一眼市场温度」，不需要精确停留或对比；原生滚动条在 Windows
    上会横切一行卡片、占掉高度，还除它之外没有任何「还有更多」的引导。指数是同类
    单值长列表（用户可选到上限 8 个），用流动承接溢出最合适。

  节奏刻意放慢且恒定（28px/s，见 indexBarModel）：
    - 恒定速度 = 选 5 个和 8 个一样快，不会「越多越快」制造紧迫感；
    - hover / focus-within 暂停（CSS），想读点位时不被带走；
    - 不溢出时静态（放得下就别晃）。

  什么时候「不动」：只有两种——设置里关掉「滚动展示」，或系统开了减弱动效。
  刻意**不**按交易时段判断：16:15 打开页面看到静态滚动条，等于「功能没生效」，
  比一直在动更让人困惑（初版踩过，见 useIndexBarMarquee 的注释）。

  无障碍：循环用的第二份内容带 aria-hidden 与 tabindex=-1，读屏与 Tab 不会重复；
  静态时退回可横向滚动的条（细滚动条，hover 才显色，内容仍能看全）。
-->
<template>
  <div
    ref="containerRef"
    class="index-market-bar__ticker"
    :class="active ? 'is-marquee' : 'is-static'"
  >
    <div
      class="index-market-bar__track"
      :class="{ 'is-anim': active }"
      :style="trackStyle"
    >
      <div
        v-for="copy in copies"
        :key="copy"
        class="index-market-bar__group"
        :aria-hidden="copy === 1 ? 'true' : undefined"
      >
        <button
          v-for="item in items"
          :key="item.meta.key"
          class="ticker-item"
          type="button"
          :class="item.trend"
          :tabindex="copy === 1 ? -1 : undefined"
          :aria-label="`${item.name}，点击查看详情`"
          @click="emit('select', item.meta)"
        >
          <span class="ticker-item__name">{{ item.name }}</span>
          <span class="ticker-item__price">{{ item.price }}</span>
          <span class="ticker-item__pct">{{ item.pct }}</span>
        </button>
      </div>
    </div>
    <span v-if="!items.length" class="index-market-bar__empty">
      未选择指数，点击齿轮添加
    </span>
  </div>
</template>

<script setup lang="ts">
import { toRef } from "vue";
import { useIndexBarMarquee } from "@/views/asset/watchlist/composables/useIndexBarMarquee";
import { useIndexBarMotionPref } from "@/views/asset/watchlist/composables/useIndexBarMotionPref";
import type { IndexTickerItem } from "@/views/asset/watchlist/composables/indexBarModel";
import type { IndexCatalogEntry } from "@/views/asset/watchlist/composables/indexCatalog";

const props = defineProps<{ items: IndexTickerItem[] }>();
const emit = defineEmits<{ (e: "select", meta: IndexCatalogEntry): void }>();

// 开关在「指数个性化设置」弹窗里，模块级单例，改动即时生效
const { enabled } = useIndexBarMotionPref();

const { containerRef, active, copies, trackStyle } = useIndexBarMarquee(
  toRef(props, "items"),
  enabled
);
</script>

<style scoped lang="scss">
.index-market-bar__ticker {
  position: relative;
  overflow: hidden;

  // 静态态：收盘 / 不溢出 / 减动效。溢出时仍能滚，只是滚动条极轻（hover 才显色）
  &.is-static {
    overflow: auto hidden;
    scrollbar-color: transparent transparent;
    scrollbar-width: thin;

    &::-webkit-scrollbar {
      height: 4px;
    }

    &::-webkit-scrollbar-track {
      background: transparent;
    }

    &::-webkit-scrollbar-thumb {
      background: transparent;
      border-radius: 4px;
    }

    &:hover {
      scrollbar-color: var(--border-default, #eee) transparent;

      &::-webkit-scrollbar-thumb {
        background: var(--border-default, #eee);
      }
    }
  }
}

.index-market-bar__track {
  display: flex;
  width: max-content;
  will-change: transform;

  &.is-anim {
    animation: index-bar-marquee var(--marquee-duration, 60s) linear infinite;
  }
}

// 悬停 / 键盘聚焦时暂停：读点位、准备点击时内容不跑
.index-market-bar__ticker:hover .index-market-bar__track.is-anim,
.index-market-bar__ticker:focus-within .index-market-bar__track.is-anim {
  animation-play-state: paused;
}

// 每份内容自带右内边距 = 项间距，保证两份拼接处缝隙一致（无缝循环）
.index-market-bar__group {
  display: flex;
  flex: 0 0 auto;
  gap: 10px;
  padding-right: 10px;
}

@keyframes index-bar-marquee {
  from {
    transform: translate3d(0, 0, 0);
  }

  to {
    transform: translate3d(var(--marquee-shift, -1000px), 0, 0);
  }
}

// 折叠态速览项：可点跳转 + 悬停反馈，单行紧凑
.ticker-item {
  display: inline-flex;
  flex-shrink: 0;
  gap: 6px;
  align-items: baseline;
  padding: 4px 10px;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: var(--bg-page, #fafafa);
  border: 1px solid var(--border-default, #eee);
  border-radius: 10px;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;

  &:hover,
  &:focus-visible {
    outline: none;
    border-color: var(--brand-500, #4a7cff);
    box-shadow: 0 2px 8px rgb(0 0 0 / 6%);
  }

  &__name {
    font-size: var(--text-label);
    font-weight: 600;
    color: var(--text-primary, #333);
  }

  &__price {
    font-size: var(--text-label);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--text-primary, #333);
  }

  // 不带显式色：继承外层 is-rise/is-fall/is-flat 的语义色
  &__pct {
    font-size: var(--text-label);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
}

// 涨跌语义色（A 股习惯：涨红跌绿），与全站 colors.css 一致
.is-rise {
  color: var(--color-rise);
}

.is-fall {
  color: var(--color-fall-ink);
}

.is-flat {
  color: var(--text-secondary, #888);
}

.index-market-bar__empty {
  display: block;
  padding: 4px 0;
  font-size: var(--text-label);
  color: var(--text-disabled, #bbb);
}
</style>
