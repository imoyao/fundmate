<!--
  IndexMarketBar · 自选页顶部大盘指数条（#watchlist banner）

  定位：常驻「市场上下文条」，与 WatchlistSummaryBar（我的持仓）上下分层，
  不与探市页「大类资产观察」的指数数字快照冲突（本条带分时 + 常驻自选页）。

  数据：复用 fundmate 既有前端实时源——
    - 腾讯指数行情 qt.gtimg.cn（fetchTencentIndexQuotes，支持 hk/us 前缀指数）
    - 东财分时 push2his（fetchIntradayTrendBySecid）
  涨跌按 A 股习惯（涨红 --color-rise / 跌绿 --color-fall），与全站一致。

  交互：每张卡片为按钮，点击跳内部详情页 /index/<symbol>（productRoute，
  assetType=index 已在 DETAIL_ASSET_TYPES 白名单内）。
-->
<template>
  <section class="index-banner" aria-label="大盘指数速览">
    <button
      v-for="meta in INDICES"
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
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive } from "vue";
import { useRouter } from "vue-router";
import {
  fetchTencentIndexQuotes,
  fetchIntradayTrendBySecid
} from "@/utils/realtimeDataSources";
import { productRoute } from "@/utils/productIdentity";

interface IndexMeta {
  key: string;
  name: string;
  /** 腾讯外部码（sh/sz/hk/us 前缀） */
  tencentCode: string;
  /** 东财分时 secid */
  secid: string;
  /** 内部详情 symbol（assetType=index） */
  detailSymbol: string;
}

const INDICES: IndexMeta[] = [
  {
    key: "sh",
    name: "上证指数",
    tencentCode: "sh000001",
    secid: "1.000001",
    detailSymbol: "SH000001"
  },
  {
    key: "sz",
    name: "深证成指",
    tencentCode: "sz399001",
    secid: "0.399001",
    detailSymbol: "SZ399001"
  },
  {
    key: "cyb",
    name: "创业板指",
    tencentCode: "sz399006",
    secid: "0.399006",
    detailSymbol: "SZ399006"
  },
  // 港股/美股指数 secid 为 best-effort（东财 overseas 口径），取数失败仅缺分时不报错
  {
    key: "hk",
    name: "恒生指数",
    tencentCode: "hkHSI",
    secid: "100.HSI",
    detailSymbol: "HKHSI"
  },
  {
    key: "ixic",
    name: "纳斯达克",
    tencentCode: "usIXIC",
    secid: "100.IXIC",
    detailSymbol: "USIXIC"
  }
];

interface IndexQuote {
  price: number;
  change: number;
  changePct: number;
  prevClose: number;
  time: string;
  spark: number[];
}

const EMPTY: IndexQuote = {
  price: NaN,
  change: NaN,
  changePct: NaN,
  prevClose: NaN,
  time: "",
  spark: []
};

const quotes = reactive<Record<string, IndexQuote>>(
  Object.fromEntries(INDICES.map(m => [m.key, { ...EMPTY }]))
);

const router = useRouter();
let timer: number | null = null;

function quoteOf(meta: IndexMeta): IndexQuote {
  return quotes[meta.key] ?? EMPTY;
}

function trendClass(meta: IndexMeta): string {
  const pct = quoteOf(meta).changePct;
  if (Number.isNaN(pct) || pct === 0) return "is-flat";
  return pct > 0 ? "is-rise" : "is-fall";
}

function strokeColor(meta: IndexMeta): string {
  const cls = trendClass(meta);
  if (cls === "is-rise") return "var(--color-rise)";
  if (cls === "is-fall") return "var(--color-fall)";
  return "var(--color-text-placeholder, #bbb)";
}

function formatPrice(v: number): string {
  if (Number.isNaN(v)) return "—";
  return v.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function formatSigned(v: number): string {
  if (Number.isNaN(v)) return "—";
  const s = v.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
  return v > 0 ? `+${s}` : s;
}

function formatPct(v: number): string {
  if (Number.isNaN(v)) return "";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function buildPath(points: number[]): string {
  if (points.length < 2) return "";
  const w = 100;
  const h = 28;
  const pad = 2;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = (w - pad * 2) / (points.length - 1);
  return points
    .map((p, i) => {
      const x = pad + i * step;
      const y = pad + (h - pad * 2) * (1 - (p - min) / range);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

/** 指数点位与昨收算涨跌额（腾讯指数行情已给昨收 parts[4]） */
function patchQuote(
  meta: IndexMeta,
  price: number,
  changePct: number,
  prevClose: number,
  time: string
): void {
  const q = quotes[meta.key];
  q.price = price;
  q.changePct = changePct;
  q.prevClose = prevClose;
  q.change =
    Number.isFinite(prevClose) && prevClose > 0 ? price - prevClose : NaN;
  q.time = time;
}

async function load(): Promise<void> {
  // 1) 指数行情（腾讯，一次批量）
  const map = await fetchTencentIndexQuotes(INDICES.map(i => i.tencentCode));
  for (const meta of INDICES) {
    const q = map.get(meta.tencentCode);
    if (q)
      patchQuote(
        meta,
        q.currentPrice,
        q.changePct,
        q.prevClose ?? NaN,
        q.updateTime
      );
  }
  // 2) 分时（东财，逐指数 best-effort；失败仅缺折线）
  await Promise.all(
    INDICES.map(async meta => {
      const t = await fetchIntradayTrendBySecid(meta.secid);
      if (t) quotes[meta.key].spark = t.points;
    })
  );
}

function goDetail(meta: IndexMeta): void {
  const path = productRoute({ assetType: "index", symbol: meta.detailSymbol });
  if (path) router.push(path);
}

function startTimer(): void {
  if (timer !== null) return;
  timer = window.setInterval(() => {
    if (!document.hidden) void load();
  }, 30_000);
}

function stopTimer(): void {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
}

onMounted(() => {
  void load();
  startTimer();
});

onUnmounted(stopTimer);
</script>

<style scoped lang="scss">
.index-banner {
  display: flex;
  gap: 12px;
  padding: 12px;

  // 与卡片内容区间距令牌保持一致（design.md 间距规范）
  margin-bottom: 12px;
  overflow-x: auto;
  background: var(--bg-card, #fff);
  border-radius: 12px;
}

.index-card {
  display: flex;
  flex: 1 1 0;
  flex-direction: column;
  gap: 4px;
  min-width: 132px;
  padding: 10px 12px;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: var(--bg-page, #fafafa);
  border: 1px solid var(--border-color, #eee);
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
  color: var(--color-text-primary, #333);
}

.index-card__time {
  font-size: var(--text-label);
  color: var(--color-text-placeholder, #bbb);
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
    color: var(--color-text-placeholder, #bbb);
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
  color: var(--color-text-secondary, #888);
}
</style>
