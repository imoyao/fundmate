/**
 * 指数条取数与格式化（#watchlist 顶部大盘指数条）。
 *
 * 把「点位 / 涨跌 / 分时折线」的取数、格式化、轮询定时器从 IndexMarketBar.vue 抽出，
 * 让组件只负责渲染与折叠交互，压住 vue-size 门禁（#980 上帝页面拆分）。
 *
 * 数据：复用 fundmate 既有前端实时源——
 *   - 腾讯指数行情 qt.gtimg.cn（fetchTencentIndexQuotes，支持 hk/us 前缀指数）
 *   - 东财分时 push2his（fetchIntradayTrendBySecid）
 * 涨跌按 A 股习惯（涨红 --color-rise / 跌绿 --color-fall），与全站一致。
 */
import { onMounted, onUnmounted, reactive, watch, type Ref } from "vue";
import { useRouter } from "vue-router";
import {
  fetchTencentIndexQuotes,
  fetchIntradayTrendBySecid
} from "@/utils/realtimeDataSources";
import { productRoute } from "@/utils/productIdentity";
import type { IndexCatalogEntry } from "@/views/asset/watchlist/composables/indexCatalog";

export interface IndexQuote {
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

export interface IndexBarQuotes {
  quoteOf: (meta: IndexCatalogEntry) => IndexQuote;
  trendClass: (meta: IndexCatalogEntry) => string;
  strokeColor: (meta: IndexCatalogEntry) => string;
  formatPrice: (v: number) => string;
  formatSigned: (v: number) => string;
  formatPct: (v: number) => string;
  buildPath: (points: number[]) => string;
  goDetail: (meta: IndexCatalogEntry) => void;
}

export function useIndexBarQuotes(
  indices: Ref<IndexCatalogEntry[]>
): IndexBarQuotes {
  const quotes = reactive<Record<string, IndexQuote>>({});
  const router = useRouter();
  let timer: number | null = null;

  function quoteOf(meta: IndexCatalogEntry): IndexQuote {
    return quotes[meta.key] ?? EMPTY;
  }

  function trendClass(meta: IndexCatalogEntry): string {
    const pct = quoteOf(meta).changePct;
    if (Number.isNaN(pct) || pct === 0) return "is-flat";
    return pct > 0 ? "is-rise" : "is-fall";
  }

  function strokeColor(meta: IndexCatalogEntry): string {
    const cls = trendClass(meta);
    if (cls === "is-rise") return "var(--color-rise)";
    if (cls === "is-fall") return "var(--color-fall)";
    return "var(--text-disabled, #bbb)";
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

  function patchQuote(
    meta: IndexCatalogEntry,
    price: number,
    changePct: number,
    prevClose: number,
    time: string
  ): void {
    const q = quotes[meta.key] ?? (quotes[meta.key] = { ...EMPTY });
    q.price = price;
    q.changePct = changePct;
    q.prevClose = prevClose;
    q.change =
      Number.isFinite(prevClose) && prevClose > 0 ? price - prevClose : NaN;
    q.time = time;
  }

  async function load(): Promise<void> {
    // 确保本轮选中的 key 都有 quotes 槽位（新增指数不会因缺槽位而报错）
    for (const meta of indices.value) {
      if (!quotes[meta.key]) quotes[meta.key] = { ...EMPTY };
    }
    // 1) 指数行情（腾讯，一次批量）
    const map = await fetchTencentIndexQuotes(
      indices.value.map(i => i.tencentCode)
    );
    for (const meta of indices.value) {
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
      indices.value.map(async meta => {
        const t = await fetchIntradayTrendBySecid(meta.secid);
        if (t) quotes[meta.key].spark = t.points;
      })
    );
  }

  function goDetail(meta: IndexCatalogEntry): void {
    const path = productRoute({
      assetType: "index",
      symbol: meta.detailSymbol
    });
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

  // 选中集合变化（弹窗保存后）→ 立即重载，新指数即时出现
  watch(indices, () => {
    void load();
  });

  onMounted(() => {
    void load();
    startTimer();
  });

  onUnmounted(stopTimer);

  return {
    quoteOf,
    trendClass,
    strokeColor,
    formatPrice,
    formatSigned,
    formatPct,
    buildPath,
    goDetail
  };
}
