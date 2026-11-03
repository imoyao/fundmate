<!--
  IndexMarketBar · 自选页顶部大盘指数条（#watchlist）

  定位：常驻「市场上下文条」，与 WatchlistSummaryBar（我的持仓）上下分层，
  不与探市页「大类资产观察」的指数数字快照冲突（本条带分时 + 常驻自选页）。

  数据：复用 fundmate 既有前端实时源——
    - 腾讯指数行情 qt.gtimg.cn（fetchTencentIndexQuotes，支持 hk/us 前缀指数）
    - 东财分时 push2his（fetchIntradayTrendBySecid）
  涨跌按 A 股习惯（涨红 --color-rise / 跌绿 --color-fall），与全站一致。

  交互：
    - 默认折叠（#watchlist banner 收起，占版面大）：折叠态是**单行跑马灯**
      （见 IndexMarketBarTicker）——内容溢出才启用、恒定 28px/s、hover 暂停、
      收盘后静态；比横向滚动条更省版面，也不会横切一行卡片。
    - 展开态是**网格换行**（auto-fill minmax 150px）：卡片尺寸恒定，不再被
      `flex: 1 1 0` 压到 132px 下限后溢出（那是「挤压在一块」的根因）。
      8 个指数约两行，故不会把下方「我的持仓」汇总条与表格推出首屏。
    - 折叠/展开状态本地记忆：用户展开过，下次进入沿用（useCollapsedState）。
    - 指数可个性化：齿轮按钮打开「指数个性化设置」弹窗，用户自选 + 排序
      （见 IndexPersonalizationDialog / useIndexBarSelection / indexCatalog），
      上限 8 个（MAX_INDEX_COUNT，理由见 indexBarModel）。
    - 每张卡片 / 速览项为按钮，点击跳内部详情页 /index/<symbol>（productRoute，
      assetType=index 已在 DETAIL_ASSET_TYPES 白名单内）。
-->
<template>
  <section class="index-market-bar" aria-label="大盘指数速览">
    <div class="index-market-bar__head">
      <span class="index-market-bar__title">大盘指数</span>
      <div class="index-market-bar__actions">
        <button
          type="button"
          class="index-market-bar__toggle index-market-bar__settings"
          aria-label="指数个性化设置"
          @click="openDialog"
        >
          <el-icon><Setting /></el-icon>
        </button>
        <button
          type="button"
          class="index-market-bar__toggle"
          :aria-expanded="expanded ? 'true' : 'false'"
          aria-controls="index-market-bar-body"
          @click="toggle"
        >
          <span>{{ expanded ? "收起" : "展开" }}</span>
          <el-icon><component :is="toggleIcon" /></el-icon>
        </button>
      </div>
    </div>

    <!-- 折叠态：单行跑马灯（溢出才动、收盘静态），点击项仍跳详情 -->
    <IndexMarketBarTicker
      v-if="!expanded"
      :items="tickerItems"
      @select="goDetail"
    />

    <!-- 展开态：完整卡片 + 分时折线 -->
    <div v-else id="index-market-bar-body" class="index-market-bar__cards">
      <button
        v-for="meta in indices"
        :key="meta.key"
        class="index-card"
        type="button"
        :aria-label="`${meta.name}，点击查看详情`"
        @click="goDetail(meta)"
      >
        <div class="index-card__head">
          <span class="index-card__name">{{ meta.name }}</span>
          <span class="index-card__time">{{ quoteOf(meta).time }}</span>
        </div>

        <div class="index-card__price" :class="trendClass(meta)">
          {{ formatPrice(quoteOf(meta).price) }}
        </div>

        <div class="index-card__chg" :class="trendClass(meta)">
          <span>{{ formatSigned(quoteOf(meta).change) }}</span>
          <span class="index-card__pct">{{
            formatPct(quoteOf(meta).changePct)
          }}</span>
        </div>

        <svg
          v-if="quoteOf(meta).spark.length >= 2"
          class="index-card__spark"
          viewBox="0 0 100 28"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path
            :d="buildPath(quoteOf(meta).spark)"
            :stroke="strokeColor(meta)"
            fill="none"
            stroke-width="1.2"
          />
        </svg>
        <div v-else class="index-card__spark index-card__spark--empty">—</div>
      </button>
    </div>

    <IndexPersonalizationDialog v-model="dialogVisible" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ArrowDown, ArrowUp, Setting } from "@element-plus/icons-vue";
import { useCollapsedState } from "@/views/asset/watchlist/composables/useCollapsedState";
import { useIndexBarSelection } from "@/views/asset/watchlist/composables/useIndexBarSelection";
import { useIndexBarQuotes } from "@/views/asset/watchlist/composables/useIndexBarQuotes";
import type { IndexTickerItem } from "@/views/asset/watchlist/composables/indexBarModel";
import IndexMarketBarTicker from "@/views/asset/watchlist/components/IndexMarketBarTicker.vue";
import IndexPersonalizationDialog from "@/views/asset/watchlist/components/IndexPersonalizationDialog.vue";

// 渲染列表 = 用户个性化选中的目录条目（按选中顺序；已剔除脏 key）
const { selectedEntries } = useIndexBarSelection();
const indices = selectedEntries;

// #watchlist banner 收起：默认折叠，省首屏版面；展开态才渲染完整卡片 + 分时折线。
// 折叠/展开状态本地记忆：用户展开过，下次进入沿用（useCollapsedState）。
const { expanded } = useCollapsedState("index-bar");
const toggleIcon = computed(() => (expanded.value ? ArrowUp : ArrowDown));
function toggle(): void {
  expanded.value = !expanded.value;
}

const dialogVisible = ref(false);
function openDialog(): void {
  dialogVisible.value = true;
}

// 取数 / 格式化 / 分时折线 / 轮询定时器（拆到 composable，压住 vue-size 门禁）
const {
  quoteOf,
  trendClass,
  strokeColor,
  formatPrice,
  formatSigned,
  formatPct,
  buildPath,
  goDetail
} = useIndexBarQuotes(indices);

// 折叠态展示模型：格式化在父层完成，跑马灯组件只负责渲染与滚动
const tickerItems = computed<IndexTickerItem[]>(() =>
  indices.value
    .filter(meta => !Number.isNaN(quoteOf(meta).price))
    .map(meta => ({
      meta,
      name: meta.name,
      price: formatPrice(quoteOf(meta).price),
      pct: formatPct(quoteOf(meta).changePct) || "—",
      trend: trendClass(meta)
    }))
);
</script>

<style scoped lang="scss">
.index-market-bar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;

  // 与卡片内容区间距令牌保持一致（design.md 间距规范）
  margin-bottom: 12px;
  background: var(--bg-card, #fff);
  border-radius: 12px;

  &__head {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
  }

  &__title {
    font-size: var(--text-label);
    font-weight: 600;
    color: var(--text-secondary, #888);
  }

  // 头部的「设置 + 展开/收起」操作组
  &__actions {
    display: inline-flex;
    gap: 6px;
    align-items: center;
  }

  // 展开/收起与设置按钮：复用 ExploreAssetOverview 的折叠交互样式（#1546 T2.2 范式）
  &__toggle {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    padding: 4px 12px;
    font-family: inherit;
    font-size: var(--text-label);
    color: var(--text-secondary, #888);
    cursor: pointer;
    background: transparent;
    border: 1px solid var(--border-light, #f0ebe4);
    border-radius: var(--radius-pill, 9999px);
    transition:
      background-color 150ms ease,
      color 150ms ease;

    &:hover {
      color: var(--text-primary, #333);
      background: var(--bg-hover, #f2ede8);
    }

    &:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
    }
  }

  // 设置（齿轮）按钮：纯图标、更紧凑
  &__settings {
    padding: 4px 8px;
  }

  // 展开态：网格换行（auto-fill 自适应列数）。
  // 不用 flex + overflow-x：`flex: 1 1 0` + min-width 会把卡片压到下限再溢出，
  // 名称与时间挤在一行、分时线被压扁——那正是「挤压在一块」的根因。
  &__cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 12px;
    animation: index-cards-in 180ms ease-out;
  }
}

// 展开瞬间轻微淡入：让高度变化可感知，但不做「下方还有内容」之类的提示动效
@keyframes index-cards-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.index-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 10px 12px;
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
}

.index-card__head {
  display: flex;
  gap: 6px;
  align-items: baseline;
  justify-content: space-between;
}

.index-card__name {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary, #333);
}

.index-card__time {
  font-size: var(--text-label);
  color: var(--text-disabled, #bbb);
}

.index-card__price {
  font-size: var(--text-num-strong);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.index-card__chg {
  display: flex;
  gap: 6px;
  align-items: baseline;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
}

.index-card__pct {
  font-weight: 600;
}

.index-card__spark {
  width: 100%;
  height: 28px;
  margin-top: 2px;

  &--empty {
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: var(--text-label);
    color: var(--text-disabled, #bbb);
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
</style>
