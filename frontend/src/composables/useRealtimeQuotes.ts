import { ref, onBeforeUnmount, type Ref } from "vue";
import {
  calculateHoldingsValuation,
  type Holding,
  type ValuationItem,
  type ValuationSummary
} from "@/utils/valuationEngine";
import { http } from "@/utils/http";

const STORAGE_KEY = "showbuy_realtime_quotes_enabled";
const REFRESH_INTERVAL_KEY = "showbuy_realtime_quotes_interval";

/**
 * 平台级总闸（issue #826：双层估值开关的平台级部分）。
 * 后端经 env `REALTIME_QUOTES_ENABLED` 配置并经 GET /api/utils/config/ 下发：
 * 数据源压力过大或合规收紧时，运维改 env 即可一键关闭全站实时估值，无需发版。
 * 平台级为总闸：关闭时强制停轮询、toggle() 无效；打开时按用户级 localStorage 偏好运行。
 *
 * 模块级缓存 + 请求去重：探市与自选两个页面各自实例化 useRealtimeQuotes，
 * 共享同一份平台开关，避免重复请求；后创建的实例可立即拿到已缓存结果。
 */
interface PlatformConfigResponse {
  data: { realtime_quotes_enabled: boolean };
  message: string;
}

let platformEnabled: boolean | null = null;
let platformConfigPromise: Promise<boolean> | null = null;

async function fetchPlatformEnabled(): Promise<boolean> {
  if (platformEnabled !== null) return platformEnabled;
  if (!platformConfigPromise) {
    platformConfigPromise = http
      .get<PlatformConfigResponse, unknown>("/api/utils/config/")
      .then(res => {
        platformEnabled = res.data.realtime_quotes_enabled;
        return platformEnabled;
      })
      .catch(() => {
        // 配置接口不可达时保守放行：保持用户级开关现状（默认开启），
        // 避免后端抖动导致前端误停所有实时估值。
        platformEnabled = true;
        return true;
      })
      .finally(() => {
        platformConfigPromise = null;
      });
  }
  return platformConfigPromise;
}

/** 可选刷新档位（秒）。默认 30s；盘中可切 15s 快速档，收盘后切 60/90s 省请求。 */
export const REFRESH_INTERVAL_OPTIONS = [15, 30, 60, 90] as const;
export const DEFAULT_REFRESH_INTERVAL = 30;

export type RefreshInterval = (typeof REFRESH_INTERVAL_OPTIONS)[number];

export interface RealtimeQuotesReturn {
  enabled: Ref<boolean>;
  toggle: (value?: boolean) => void;
  status: Ref<"idle" | "trading" | "closed" | "error">;
  items: Ref<ValuationItem[]>;
  summary: Ref<ValuationSummary | null>;
  lastUpdateTime: Ref<string>;
  refreshInterval: Ref<RefreshInterval>;
  setRefreshInterval: (seconds: RefreshInterval) => void;
  manualRefresh: () => Promise<void>;
}

function readStoredInterval(): RefreshInterval {
  const raw = localStorage.getItem(REFRESH_INTERVAL_KEY);
  const n = Number(raw);
  return (REFRESH_INTERVAL_OPTIONS as readonly number[]).includes(n)
    ? (n as RefreshInterval)
    : DEFAULT_REFRESH_INTERVAL;
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
  const refreshInterval = ref<RefreshInterval>(readStoredInterval());

  let timer: number | null = null;

  // 🎯 终极绝杀：直接管理状态，抛弃原本可能报错的逻辑
  // 这个 toggle 没有任何 try-catch 异步陷阱，保证点击后状态1毫秒内立刻改变
  const toggle = (value?: boolean) => {
    // 平台级总闸已确认关闭时：用户级开关整体失效，点击也不开启（issue #826）。
    // 总闸尚未确认（platformEnabled 仍为 null）时放行，配置返回后由
    // 下方 fetchPlatformEnabled().then 兜底强制关闭。
    if (platformEnabled === false) return;
    const nextEnabled = value ?? !enabled.value;
    enabled.value = nextEnabled;
    localStorage.setItem(STORAGE_KEY, String(nextEnabled));

    if (nextEnabled) {
      start(); // 开启
    } else {
      stop(); // 关闭
    }
  };

  // 仅停止轮询定时器，不清空已有行情数据（收盘/休市保留最近一次数据）
  const stopPolling = () => {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  };

  // 本地时区日期（YYYY-MM-DD）。用 toISOString 取 UTC 日期在凌晨会跨日误判，
  // 与 realtimeDataSources.isToday 的修复保持一致。
  const localDateStr = (d: Date): string =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
      d.getDate()
    ).padStart(2, "0")}`;

  const isTradingDay = async (): Promise<boolean> => {
    try {
      const today = localDateStr(new Date());
      const res = await http.get(`/api/utils/trading-days/${today}/`);
      return (res as any)?.data?.is_trading_day === true;
    } catch {
      const day = new Date().getDay();
      return day !== 0 && day !== 6;
    }
  };

  // 按当前档位启动盘中轮询（tick 内自行判断收盘/休市并停止）
  const schedulePolling = () => {
    stopPolling();
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
        // 收盘/休市：停止轮询并标记状态，但保留最近一次行情数据（收盘价 / 基金预估值）
        stopPolling();
        status.value = "closed";
        return;
      }
      await fetchAndUpdate();
    }, refreshInterval.value * 1000);
  };

  // 切换刷新档位：持久化 + 仅盘中轮询中按新档位重启定时器（收盘/休市下次 start 自动生效）
  const setRefreshInterval = (seconds: RefreshInterval) => {
    refreshInterval.value = seconds;
    localStorage.setItem(REFRESH_INTERVAL_KEY, String(seconds));
    if (timer) {
      schedulePolling();
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
    stopPolling();

    await fetchAndUpdate();

    const trading = await isTradingDay();
    if (!trading) {
      status.value = "closed";
      return; // 这里直接返回，不启动轮询，但绝不改变 enabled.value
    }

    schedulePolling();
  };

  // ✅ 用户主动关闭实时估值时：停止轮询并清空数据（此后表格回退到后端静态 current_price）
  const stop = () => {
    stopPolling();
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

  // 平台级总闸异步拉取：返回后若平台关闭，强制停轮询并置 enabled=false，
  // 使前端（含匿名探市页）尊重后端一键关闭（改 env 即可、无需发版）。
  // enabled 初始值仍取 localStorage 用户级偏好，待总闸确认后再覆盖。
  void fetchPlatformEnabled().then(platformOn => {
    if (!platformOn && enabled.value) {
      stop();
      enabled.value = false;
    }
  });

  onBeforeUnmount(() => stopPolling());

  return {
    enabled,
    toggle,
    status,
    items,
    summary,
    lastUpdateTime,
    refreshInterval,
    setRefreshInterval,
    manualRefresh
  };
}
