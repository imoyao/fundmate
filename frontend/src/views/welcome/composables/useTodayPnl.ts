// src/views/welcome/composables/useTodayPnl.ts
/**
 * 首页「最新收益」卡的数据域（#今日收益卡）。
 *
 * 三段职责，边界写死：
 * 1. **取数**：后端 `/api/summary/today-pnl/` 是当日盈亏的唯一口径（与收益日历同源）；
 * 2. **盘中跳动**：复用平台级 `useRealtimeQuotes`（不自己起 setInterval——那会变成
 *    与自选页并发的第二条轮询链），只把实时价**替换**进后端结果（见 todayPnlOverlay）；
 * 3. **收盘后确认**：轮询在收盘那一刻停掉，改为低频（5min）问后端，
 *    等官方净值落地、状态翻 `confirmed` 就停——不需要用户手动刷新。
 *
 * 轮询成本：批量源（基金 50 只/请求、股票 1 请求）走 `useRealtimeQuotes` 既有底座；
 * 首页默认开启实时（`defaultEnabled`），但用户显式关过就尊重（同一份全局偏好）。
 */

import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { getTodayPnl, type TodayPnlData } from "@/api/summary";
import { useRealtimeQuotes } from "@/composables/useRealtimeQuotes";
import {
  applyPriceOverlay,
  shanghaiTodayIso,
  todayPnlSubtitle
} from "./todayPnlOverlay";

/** 官方净值公布时间不定（19:00~23:00 都有），收盘后低频问一次即可 */
const CONFIRM_POLL_MS = 5 * 60 * 1000;
/** 过了这个点还确认不了就不再打扰（净值异常 / 停更，留给收益日历去暴露） */
const CONFIRM_POLL_UNTIL_HOUR = 23;
const CONFIRM_POLL_UNTIL_MINUTE = 30;

export function useTodayPnl() {
  const data = ref<TodayPnlData | null>(null);
  const loading = ref(false);
  /** 只有「一次都没成功过」才算错误态：盘中抖动不该把已有数字清成加载失败 */
  const error = ref(false);

  async function fetchTodayPnl(): Promise<void> {
    loading.value = true;
    try {
      const res = await getTodayPnl();
      data.value = res?.data ?? null;
      error.value = data.value == null;
    } catch {
      error.value = data.value == null;
    } finally {
      loading.value = false;
    }
  }

  /** 后端当日取价索引（实时行情缺失时的兜底价 + 价格替换的基准） */
  const holdingBySymbol = computed(
    () => new Map((data.value?.holdings ?? []).map(h => [h.symbol, h]))
  );

  const realtime = useRealtimeQuotes(
    () =>
      (data.value?.holdings ?? []).map(h => ({
        symbol: h.symbol,
        type: h.class === "fund" ? ("fund" as const) : ("stock" as const),
        quantity: h.quantity,
        // 卡片不展示成本，也不该用它算任何东西（盈亏由后端给）
        costPrice: 0
      })),
    symbol => {
      const item = holdingBySymbol.value.get(symbol);
      return item
        ? { currentPrice: item.price, changePct: 0, prevClose: null }
        : undefined;
    },
    { defaultEnabled: true }
  );

  /** 实时价（只取真拿到行情的那些；静态兜底价与后端同日价相等，替换没有意义） */
  const realtimePrices = computed(() => {
    const prices = new Map<string, number>();
    for (const item of realtime.items.value) {
      if (item.source === "realtime" && item.currentPrice > 0) {
        prices.set(item.symbol, item.currentPrice);
      }
    }
    return prices;
  });

  const overlay = computed(() => {
    if (!data.value) return { data: null, applied: false };
    return applyPriceOverlay(data.value, realtimePrices.value, {
      // 后端日期不是今天（盘中今日无价）时，实时增量代表**今天**的全量收益，
      // 只能替换、不能叠到昨天那笔上
      replaceBase: data.value.is_today === false,
      todayIso: shanghaiTodayIso()
    });
  });

  const view = computed<TodayPnlData | null>(() => overlay.value.data);

  /** 盘中跳动是否生效（仅在交易时段 + 真拿到实时价时成立） */
  const live = computed(
    () => overlay.value.applied && realtime.status.value === "trading"
  );

  const subtitle = computed(() => {
    const current = view.value;
    if (!current) return "";
    if (live.value) {
      return realtime.lastUpdateTime.value
        ? `盘中估值 · 更新于 ${realtime.lastUpdateTime.value}`
        : "盘中估值 · 随行情刷新";
    }
    return todayPnlSubtitle({
      status: current.status,
      isToday: current.is_today,
      date: current.date
    });
  });

  // ── 收盘后低频确认：状态翻 confirmed 即停（用户不用手动刷新）──
  let confirmTimer: number | null = null;
  const stopConfirmPolling = () => {
    if (confirmTimer !== null) {
      window.clearInterval(confirmTimer);
      confirmTimer = null;
    }
  };
  const withinConfirmWindow = () => {
    const now = new Date();
    const cutoff = new Date(now);
    cutoff.setHours(CONFIRM_POLL_UNTIL_HOUR, CONFIRM_POLL_UNTIL_MINUTE, 0, 0);
    return now < cutoff;
  };
  const startConfirmPolling = () => {
    if (confirmTimer !== null) return;
    if (!withinConfirmWindow()) return;
    confirmTimer = window.setInterval(() => {
      if (document.visibilityState === "hidden") return; // 后台不查
      if (data.value?.status === "confirmed") {
        stopConfirmPolling();
        return;
      }
      void fetchTodayPnl();
    }, CONFIRM_POLL_MS);
  };

  watch(
    () => realtime.status.value,
    status => {
      if (status === "closed") startConfirmPolling();
    }
  );
  watch(
    () => data.value?.status,
    status => {
      if (status === "confirmed") stopConfirmPolling();
    }
  );

  // 切回前台补一次：离开期间可能已收盘 / 净值已公布（定时器在后台是空转的）
  const onVisibility = () => {
    if (document.visibilityState === "visible" && live.value === false) {
      void fetchTodayPnl();
    }
  };

  onMounted(() => {
    void fetchTodayPnl();
    document.addEventListener("visibilitychange", onVisibility);
  });
  onBeforeUnmount(() => {
    stopConfirmPolling();
    document.removeEventListener("visibilitychange", onVisibility);
  });

  return {
    data,
    view,
    loading,
    error,
    live,
    subtitle,
    realtime,
    refresh: fetchTodayPnl
  };
}
