import { ref, onBeforeUnmount, type Ref } from "vue";
import {
  calculateHoldingsValuation,
  type Holding,
  type ValuationItem,
  type ValuationSummary
} from "@/utils/valuationEngine";
import { http } from "@/utils/http";

const STORAGE_KEY = "showbuy_realtime_quotes_enabled";

export interface RealtimeQuotesReturn {
  enabled: Ref<boolean>;
  toggle: (value?: boolean) => void;
  status: Ref<"idle" | "trading" | "closed" | "error">;
  items: Ref<ValuationItem[]>;
  summary: Ref<ValuationSummary | null>;
  lastUpdateTime: Ref<string>;
  manualRefresh: () => Promise<void>;
}

export function useRealtimeQuotes(
  getHoldings: () => Holding[],
  getStaticPrice: (
    symbol: string
  ) => { currentPrice?: number; changePct?: number } | undefined
): RealtimeQuotesReturn {
  const enabled = ref(localStorage.getItem(STORAGE_KEY) === "true");
  const status = ref<"idle" | "trading" | "closed" | "error">("idle");
  const items = ref<ValuationItem[]>([]);
  const summary = ref<ValuationSummary | null>(null);
  const lastUpdateTime = ref("");

  let timer: number | null = null;

  // 🎯 终极绝杀：直接管理状态，抛弃原本可能报错的逻辑
  // 这个 toggle 没有任何 try-catch 异步陷阱，保证点击后状态1毫秒内立刻改变
  const toggle = (value?: boolean) => {
    const nextEnabled = value ?? !enabled.value;
    enabled.value = nextEnabled;
    localStorage.setItem(STORAGE_KEY, String(nextEnabled));

    if (nextEnabled) {
      start(); // 开启
    } else {
      stop(); // 关闭
    }
  };

  const isTradingDay = async (): Promise<boolean> => {
    try {
      const today = new Date().toISOString().slice(0, 10);
      const res = await http.get(`/api/utils/trading-days/${today}/`);
      return (res as any)?.data?.is_trading_day === true;
    } catch {
      const day = new Date().getDay();
      return day !== 0 && day !== 6;
    }
  };

  const fetchAndUpdate = async () => {
    const holdings = getHoldings();
    if (holdings.length === 0) return;
    const result = await calculateHoldingsValuation(holdings, getStaticPrice);
    items.value = result.items;
    summary.value = result.summary;
    if (result.summary?.updateTime) {
      lastUpdateTime.value = result.summary.updateTime;
    }
    if (result.summary?.source === "realtime") {
      status.value = "trading";
    } else {
      const trading = await isTradingDay();
      status.value = trading ? "error" : "closed";
    }
  };

  // ✅ 核心修复 2：start 中自动休市时，只影响 status，绝对不改变 enabled 的物理状态
  const start = async () => {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }

    await fetchAndUpdate();

    const trading = await isTradingDay();
    if (!trading) {
      status.value = "closed";
      return; // 这里直接返回，不启动轮询，但绝不改变 enabled.value
    }

    timer = window.setInterval(async () => {
      const now = new Date();
      const hour = now.getHours();
      const minute = now.getMinutes();
      const day = now.getDay();
      if (
        day === 0 ||
        day === 6 ||
        hour >= 15 ||
        hour < 9 ||
        (hour === 9 && minute < 30)
      ) {
        stop(); // 自动休市时，只清定时器
        status.value = "closed";
        return;
      }
      await fetchAndUpdate();
    }, 10000);
  };

  // ✅ 核心修复 3：用户主动关闭时，停止一切并清空数据
  const stop = () => {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    status.value = "idle";
    items.value = [];
    summary.value = null;
    lastUpdateTime.value = "";
  };

  const manualRefresh = async () => {
    if (!enabled.value) return;
    await fetchAndUpdate();
  };

  if (enabled.value) {
    start();
  }

  onBeforeUnmount(() => stop());

  return {
    enabled,
    toggle,
    status,
    items,
    summary,
    lastUpdateTime,
    manualRefresh
  };
}
