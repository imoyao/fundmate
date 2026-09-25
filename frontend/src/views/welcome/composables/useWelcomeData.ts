import { ref, onUnmounted, computed } from "vue";
import { getSummary } from "@/api/summary";
import { getPortfolioXirr, type XirrData } from "@/api/performance";
import { getTemperatureOverview } from "@/api/temperature";
import { getRecordStats } from "@/api/users";
import type { SummaryData } from "@/api/types";
import { useOverviewStore } from "@/store/modules/overview";
import { useUserStoreHook } from "@/store/modules/user";

/** 欢迎语状态：loading=加载中 / empty=未记账 / data=有数据 */
export type WelcomeState = "loading" | "empty" | "data";

/** 短/中/长期温度分解（P3 行内三连；仅消费后端 value/level，颜色令牌留前端） */
export type TempBand = { name: string; value: number | null; level: string };

/** 概览级综合温度（第二排右卡） */
export type CompositeTemperature = { value: number; level: string };

/** 温度三段位结构（后端 temperature_bands） */
export type TemperatureBands = {
  short?: TempBand;
  medium?: TempBand;
  long?: TempBand;
};

/** 近期动态 feed 条目（真实数据派生，避免空壳） */
export type HomeFeedItem = { key: string; text: string; color: string };

/** 心理账户展示条目（金额格式化交给模板中的 MoneyDisplay 组件） */
export type MentalAccountItem = {
  name: string;
  amount: number;
  percent: number;
  color: string;
};

/**
 * 首页数据单体（#980 拆分）：欢迎语 / 播报 ticker / 汇总 / XIRR / 温度 /
 * 心理账户 / 近期动态的全部状态与请求。API 拉取与 ticker 启动仍由页面
 * index.vue 在 onMounted 中按原顺序编排；ticker 计时器的清理内聚在本
 * composable（onUnmounted），避免泄漏到页面级。
 */
export function useWelcomeData() {
  // ===== 数据 =====
  const summary = ref<SummaryData | null>(null);
  const portfolioXirr = ref<XirrData | null>(null);
  // #1354：年化收益是否纳入现金等价物（货币基金/逆回购/现金）；默认 false=仅主动投资，反映真实投资水准
  const includeCashEquivalents = ref(false);

  // ===== 首页欢迎语（见 docs/design/welcome-greeting-spec.md v1.2） =====
  const recordDays = ref(0);
  const recordLoading = ref(true);
  // 未读站内信（状态三，可选迭代；当前 lay-notice 为前端示例数据，此处预留钩子）
  const hasUnread = ref(false);
  const unreadCount = ref(0);

  const welcomeState = computed<WelcomeState>(() =>
    recordLoading.value ? "loading" : recordDays.value > 0 ? "data" : "empty"
  );

  const greetingText = computed(() => {
    const h = new Date().getHours();
    if (h >= 5 && h < 12) return "早上好";
    if (h >= 12 && h < 18) return "下午好";
    if (h >= 18 && h < 22) return "晚上好";
    return "夜深了";
  });

  // 用户昵称：未设置时回退为「你」，保持原有句式，零打扰
  const userTitle = computed(() => useUserStoreHook().nickname || "你");

  // ===== 首页消息播报（ticker）：真实数据派生，轮动展示 =====
  // 原则：能算的算真实，算不了的标「即将上线」，不展示编造数字。
  const homeMessages = ref<string[]>([]);
  const tickerIndex = ref(0);
  let tickerTimer: ReturnType<typeof setInterval> | null = null;

  const currentHomeMessage = computed(() => {
    const list = homeMessages.value;
    if (list.length === 0) return "数据加载中，稍后为你播报…";
    return list[tickerIndex.value % list.length];
  });

  /** 汇总各异步接口已返回的真实数据，组装播报消息（各 fetch 完成后调用） */
  const buildHomeMessages = () => {
    const msgs: string[] = [];
    if (summary.value) {
      const assets = summary.value.total_assets_cny;
      msgs.push(
        `家庭总资产 ${assets.toLocaleString("zh-CN", { maximumFractionDigits: 0 })} 元`
      );
      const pnl = summary.value.total_pnl_cny;
      if (pnl !== 0) {
        msgs.push(
          `累计盈亏 ${pnl > 0 ? "+" : ""}${pnl.toLocaleString("zh-CN", { maximumFractionDigits: 0 })} 元`
        );
      }
    }
    if (portfolioXirr.value?.xirr != null) {
      const x = Number(portfolioXirr.value.xirr);
      msgs.push(`年化收益率（XIRR）${(x * 100).toFixed(2)}%`);
    }
    if (compositeTemperature.value) {
      const value = compositeTemperature.value.value;
      const level = compositeTemperature.value.level || "未知";
      msgs.push(
        `市场温度 ${value != null ? value.toFixed(1) : "--"}°，${level}`
      );
    }
    if (temperatureConclusion.value) {
      msgs.push(temperatureConclusion.value);
    }
    if (recordDays.value > 0) {
      msgs.push(`你已连续记账 ${recordDays.value} 天，坚持就是复利`);
    }
    homeMessages.value = msgs;
    tickerIndex.value = 0;
  };

  const startTicker = () => {
    tickerTimer = setInterval(() => {
      if (homeMessages.value.length > 1) {
        tickerIndex.value = (tickerIndex.value + 1) % homeMessages.value.length;
      }
    }, 5000);
  };

  onUnmounted(() => {
    if (tickerTimer) {
      clearInterval(tickerTimer);
      tickerTimer = null;
    }
  });

  // 综合市场温度（第二排右卡）
  const compositeTemperature = ref<CompositeTemperature | null>(null);

  // B1/P3: 短/中/长期温度分解（概览页行内三连）。仅消费后端 value/level，颜色令牌留前端。
  const temperatureBands = ref<TemperatureBands | null>(null);

  // B3: 综合温度环下方结论副文案（后端 conclusion 归集，前端不写死）
  const temperatureConclusion = ref("");

  // level → 温度语义色令牌（B3 边界：色令牌留前端，禁后端下发颜色码）
  const levelColorVar: Record<string, string> = {
    偏低: "var(--temp-low-ink)",
    适中: "var(--temp-mid-ink)",
    偏高: "var(--temp-high-ink)",
    未知: "var(--text-tertiary)"
  };
  const levelBgVar: Record<string, string> = {
    偏低: "var(--temp-low-bg)",
    适中: "var(--temp-mid-bg)",
    偏高: "var(--temp-high-bg)",
    未知: "var(--bg-soft)"
  };
  const bandPillStyle = (level: string) => ({
    color: levelColorVar[level] || levelColorVar["未知"],
    backgroundColor: levelBgVar[level] || levelBgVar["未知"]
  });

  // 心理账户：接入 overview store（store 内为示例数据，待后端提供真实接口）
  const overviewStore = useOverviewStore();
  const mentalAccounts = computed<MentalAccountItem[]>(() => {
    const accounts = overviewStore.psychAccount.accounts;
    const parsed = accounts.map(a => ({
      name: a.label,
      tone: a.tone,
      amount: Number(String(a.value).replace(/[^\d.]/g, "")) || 0
    }));
    const total = parsed.reduce((s, a) => s + a.amount, 0) || 1;
    const toneColor: Record<string, string> = {
      safe: "var(--color-success)",
      neutral: "var(--brand-700)",
      warning: "var(--color-warning-ink)",
      danger: "var(--color-danger)"
    };
    return parsed.map(a => ({
      name: a.name,
      amount: a.amount, // 金额格式化交给模板中的 MoneyDisplay 组件
      percent: Math.round((a.amount / total) * 100),
      color: toneColor[a.tone] || "var(--brand-700)"
    }));
  });

  // ===== 近期动态 feed：真实数据派生，避免空壳（后端事件日志就绪后可替换为事件流） =====
  const homeFeed = computed<HomeFeedItem[]>(() => {
    const items: HomeFeedItem[] = [];
    if (summary.value) {
      const pnl = summary.value.total_pnl_cny;
      items.push({
        key: "pnl",
        text: `累计盈亏 ${pnl >= 0 ? "+" : ""}${pnl.toLocaleString("zh-CN", { maximumFractionDigits: 0 })} 元`,
        color: pnl >= 0 ? "var(--color-rise)" : "var(--color-fall)"
      });
    }
    if (portfolioXirr.value?.xirr != null) {
      const x = Number(portfolioXirr.value.xirr);
      items.push({
        key: "xirr",
        text: `年化收益率（XIRR）${(x * 100).toFixed(2)}%`,
        color: x >= 0 ? "var(--color-rise)" : "var(--color-fall)"
      });
    }
    if (compositeTemperature.value) {
      const value = compositeTemperature.value.value;
      const level = compositeTemperature.value.level || "未知";
      items.push({
        key: "temperature",
        text: `市场温度 ${value != null ? value.toFixed(1) : "--"}°，${level}`,
        color: levelColorVar[level] || "var(--text-tertiary)"
      });
    }
    if (recordDays.value > 0) {
      items.push({
        key: "record-days",
        text: `已连续记账 ${recordDays.value} 天`,
        color: "var(--brand-700)"
      });
    }
    if (temperatureConclusion.value) {
      items.push({
        key: "conclusion",
        text: temperatureConclusion.value,
        color: "var(--text-tertiary)"
      });
    }
    return items;
  });

  // ===== API 请求 =====
  const fetchRecordStats = async () => {
    recordLoading.value = true;
    try {
      const res = await getRecordStats();
      recordDays.value = res.data?.record_days ?? 0;
    } catch (e) {
      // 欢迎语非关键路径：失败静默降级，保持品牌定调语
      console.debug("Failed to fetch record stats:", e);
      recordDays.value = 0;
    } finally {
      recordLoading.value = false;
      buildHomeMessages();
    }
  };

  const fetchSummary = async () => {
    try {
      const res = await getSummary();
      summary.value = res.data;
    } catch (e) {
      console.error("Failed to fetch summary:", e);
    } finally {
      buildHomeMessages();
    }
  };

  const fetchXirr = async () => {
    try {
      const res = await getPortfolioXirr(
        "portfolio",
        undefined,
        includeCashEquivalents.value
      );
      portfolioXirr.value = res.data;
    } catch (e) {
      console.error("获取年化收益率失败", e);
    } finally {
      buildHomeMessages();
    }
  };

  // 综合市场温度（首页概览级，只取综合值，轻量）
  const fetchTemperature = async () => {
    try {
      const res = await getTemperatureOverview();
      const data = res.data;
      if (!data) return;
      const composite = data.composites?.composite_temperature;
      if (composite) {
        compositeTemperature.value = {
          value: composite.value,
          level: composite.level || ""
        };
      }
      const bands = data.composites?.temperature_bands;
      if (bands) {
        temperatureBands.value = {
          short: bands.short
            ? {
                name: bands.short.name,
                value: bands.short.value,
                level: bands.short.level || ""
              }
            : undefined,
          medium: bands.medium
            ? {
                name: bands.medium.name,
                value: bands.medium.value,
                level: bands.medium.level || ""
              }
            : undefined,
          long: bands.long
            ? {
                name: bands.long.name,
                value: bands.long.value,
                level: bands.long.level || ""
              }
            : undefined
        };
      }
      temperatureConclusion.value = data.conclusion || "";
    } catch (e) {
      console.error("获取市场温度失败:", e);
    } finally {
      buildHomeMessages();
    }
  };

  return {
    // 欢迎语
    recordDays,
    welcomeState,
    greetingText,
    userTitle,
    hasUnread,
    unreadCount,
    // 播报 ticker
    tickerIndex,
    currentHomeMessage,
    startTicker,
    // 汇总 / XIRR
    summary,
    portfolioXirr,
    includeCashEquivalents,
    // 温度
    compositeTemperature,
    temperatureBands,
    temperatureConclusion,
    bandPillStyle,
    // 派生列表
    mentalAccounts,
    homeFeed,
    // 请求入口（页面 onMounted 编排，保持拆分前的调用顺序）
    fetchSummary,
    fetchXirr,
    fetchTemperature,
    fetchRecordStats
  };
}
