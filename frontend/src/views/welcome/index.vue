<template>
  <div
    class="welcome-container p-4 md:p-8 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 顶部欢迎语（规范：docs/design/welcome-greeting-spec.md v1.2） -->
    <WelcomeGreeting
      :welcome-state="welcomeState"
      :has-unread="hasUnread"
      :unread-count="unreadCount"
      :user-title="userTitle"
      :greeting-text="greetingText"
      :record-days="recordDays"
      :ticker-index="tickerIndex"
      :current-home-message="currentHomeMessage"
    />

    <!-- ===== 第一排：核心资产看板 + 收益趋势（饼图在子组件内，数据就绪后由本页触发首绘） ===== -->
    <!-- #2034：不再透传 distributions——首页资产看板的结构环形图已移除，
         结构拆解归资产总览（见 page-split-welcome-vs-panorama-2026-08-13.md）。 -->
    <WelcomeAssetBoard
      ref="assetBoardRef"
      :summary="summary"
      :error="summaryError"
      @retry="onRetryAsset"
    />

    <!-- ===== 第二排：年化收益追踪 + 市场温度（同一层级） ===== -->
    <WelcomeXirrTemperature
      v-model:includeCashEquivalents="includeCashEquivalents"
      :portfolio-xirr="portfolioXirr"
      :composite-temperature="compositeTemperature"
      :temperature-bands="temperatureBands"
      :temperature-conclusion="temperatureConclusion"
      :band-pill-style="bandPillStyle"
      :error="xirrError"
      @change="fetchXirr"
      @retry="onRetryAsset"
    />

    <!-- ===== 第三排：收益日历（#1812，满宽 12 列）=====
         日频派生洞察按分层原则放首页看板；满宽是硬约束（7 列月历 + 格内双信息）。 -->
    <div class="mb-8">
      <PnlCalendar />
    </div>

    <!-- ===== 第四排：持仓市值最大资产（含「添加自选」弹窗）===== -->
    <WelcomeWatchlistSection />

    <!-- ===== 第四排：财务晴雨表 + 心理账户（统一 12 列栅格 + 等宽右栏） ===== -->
    <WelcomeFinanceFeed
      :home-feed="homeFeed"
      :mental-accounts="mentalAccounts"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import PnlCalendar from "@/components/PnlCalendar/index.vue";
import WelcomeGreeting from "./components/WelcomeGreeting.vue";
import WelcomeAssetBoard from "./components/WelcomeAssetBoard.vue";
import WelcomeXirrTemperature from "./components/WelcomeXirrTemperature.vue";
import WelcomeFinanceFeed from "./components/WelcomeFinanceFeed.vue";
import WelcomeWatchlistSection from "./components/WelcomeWatchlistSection.vue";
import { useWelcomeData } from "./composables/useWelcomeData";

defineOptions({
  name: "Welcome"
});

// 页面状态单体：欢迎语 / 播报 / 汇总 / XIRR / 温度 / 派生列表（#980 拆分）
const {
  summary,
  portfolioXirr,
  includeCashEquivalents,
  recordDays,
  welcomeState,
  greetingText,
  userTitle,
  hasUnread,
  unreadCount,
  tickerIndex,
  currentHomeMessage,
  startTicker,
  compositeTemperature,
  temperatureBands,
  temperatureConclusion,
  bandPillStyle,
  homeFeed,
  mentalAccounts,
  fetchSummary,
  fetchXirr,
  fetchTemperature,
  fetchRecordStats,
  fetchUnreadNotifications,
  summaryError,
  xirrError,
  retryAssetLoad
} = useWelcomeData();

// 资产分布饼图：echarts 实例在 WelcomeAssetBoard 内，汇总数据就绪后经其 expose 的 render 首绘
const assetBoardRef = ref<InstanceType<typeof WelcomeAssetBoard> | null>(null);

// 资产关键数据重试（#1832）：重拉汇总 + 年化。
// 饼图重绘不再需要显式调用——图表收敛到 AssetAllocationDonut 后（#1902），
// 组件自己 watch data 重绘，props 变化即触发。
const onRetryAsset = async () => {
  await retryAssetLoad();
};

// ===== 生命周期（顺序与拆分前一致：汇总 → 其余并行；ticker 清理在 composable 内） =====
onMounted(() => {
  fetchSummary();
  fetchXirr();
  fetchTemperature();
  fetchRecordStats();
  fetchUnreadNotifications();
  startTicker();
});
</script>

<style lang="scss" scoped>
/* 跨子组件的深度样式与 fade-up 动画都收在这个 partial 里（#980 批 B10）。
   注意 `:deep()` 的 scope id 来自本文件，partial 只是被 `@use` 内联进来。 */
@use "./styles/welcome-deep";
</style>
