import {
  ref,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  type Ref
} from "vue";
import {
  calculateHoldingsValuation,
  type Holding,
  type ValuationItem,
  type ValuationSummary
} from "@/utils/valuationEngine";
import { http } from "@/utils/http";
import { formatDate } from "@/utils/date";

const STORAGE_KEY = "showbuy_realtime_quotes_enabled";
const REFRESH_INTERVAL_KEY = "showbuy_realtime_quotes_interval";

/**
 * 平台级总闸（issue #826：双层估值开关的平台级部分）。
 * 后端经 env `REALTIME_QUOTES_ENABLED` 配置并经 GET /api/utils/config/ 下发：
 * 数据源压力过大或合规收紧时，运维改 env 即可一键关闭全站实时估值，无需发版。
 * 平台级为总闸：关闭时强制停轮询、toggle() 无效；打开时按用户级 localStorage 偏好运行。
 *
 * 模块级缓存 + 请求去重：各消费页（探市 / 自选 / 全面盘点 / …）各自实例化
 * useRealtimeQuotes，共享同一份平台开关，避免重复请求；后创建的实例可立即拿到
 * 已缓存结果。
 *
 * **为什么不把它做成单例（#1104 公共层实测后决定）**：各页的 `getHoldings` 闭包不同、
 * 取的是各自的持仓集合，合并成一个轮询就得引入「订阅者注册 + holdings 并集 + 结果按
 * symbol 回投」三层机制；而实例数早已被 keep-alive 语义天然限制为「同一时刻只有一个
 * 在跑」——只要 `onDeactivated` 停轮询到位（见文件末尾），多实例并存就只剩「一个活跃 +
 * 若干已失活」，没有并发重复请求。用单例换这份复杂度不划算（conventions §16.2 不过度工程）。
 *
 * 因此**新增消费页的正确姿势只有一个**：在页面 setup 顶层调用本组合式函数，
 * 不要绕过它自己起 setInterval——那会真的变成并发轮询。
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

  /**
   * 是否处于 keep-alive 失活态（#1104 公共层）。
   *
   * 用途只有一个：区分「组件首次挂载后触发的 onActivated」与「从缓存页切回来的
   * onActivated」——前者 setup 里已经 start() 过，再跑一次就是重复取数。
   */
  let deactivated = false;

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
  // 与 realtimeDataSources.isToday 的修复保持一致；统一走公共 formatDate。
  const localDateStr = (d: Date): string => formatDate(d);

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

  /**
   * 单飞闸（#1860）：一轮取数在途时，后来的触发只并入这一轮，不开第二条链。
   *
   * 双触发源实证：`useWatchlistValuation` 同时监听 items 与 allItems，而 fetchData
   * 里 allItems 晚一拍才填——一次数据刷新会连开两次 manualRefresh，两条兜底链并发
   * 打外部行情源（E2E 实测 fundcomapi 60ms 内连发两枪）。双倍行情 API 只是表症，
   * 更隐蔽的是它让 E2E「切走后不再打行情接口」的正向对照在同一轮内秒过，点击落在
   * 链飞行中，空桩 JSONP 每腿 5s 的超时尾巴（fundcomapi→fundgz→qt ≈ 10s）越过
   * 3s settle 落进零请求窗口——本闸让链数回到设计值 1。
   */
  let inflightFetch: Promise<void> | null = null;
  const fetchAndUpdate = async (): Promise<void> => {
    if (inflightFetch) return inflightFetch;
    inflightFetch = (async () => {
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
    })();
    try {
      await inflightFetch;
    } finally {
      inflightFetch = null;
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

  /**
   * keep-alive 的激活 / 失活（#1104 公共层，此前缺失）：
   * `/watchlist`、`/panorama`、`/dividends` 都是 `keepAlive: true`
   * （`router/modules/home.ts`），切走时组件**不卸载**——`onBeforeUnmount` 根本不触发，
   * 于是定时器继续按 30s 一次打行情接口，而此时新页面自己的实例也在轮询，等于双份。
   * 消费者每多一处（#1104 把持仓双线接进账户详情 / 组合 / 策略后）这个放大就越明显。
   *
   * - 失活：只停定时器，**不清空已取到的行情**（`stop()` 会清空）——用户切回来时
   *   表格里仍是刚才那份估值，不会先闪一下空值再补上。
   * - 激活：走 `start()` 而不是裸启定时器——离开期间可能已收盘、刷新档位也可能
   *   在别的页面被改过，`start()` 会按当前状态重新判定。
   *
   * 非 keep-alive 组件上这两个钩子不会被调用，注册无副作用（`/inventory` 即此类）。
   */
  onDeactivated(() => {
    deactivated = true;
    stopPolling();
  });

  onActivated(() => {
    // 首次挂载：setup 里已 start()，此处只消费标记不再重复取数
    if (!deactivated) return;
    deactivated = false;
    if (enabled.value) void start();
  });

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
