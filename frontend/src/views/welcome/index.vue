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
    <WelcomeAssetBoard
      ref="assetBoardRef"
      :summary="summary"
      :distributions="distributions"
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

    <!-- ===== 第四排：持仓市值最大资产 ===== -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-8">
      <!-- 持仓市值最大资产（风险预警改由顶部消息播报承载，本页不再保留静态风险热力图） -->
      <div
        class="lg:col-span-12 flex flex-col gap-3 card-hover card-enter h-full"
      >
        <!-- info tooltip 承载「怎么置顶 / 怎么取消置顶」这类指引（#1954）。
             此前这段说明是WatchlistWidget 内部一块带 border-b 的文字区，与表头线
             挤在一起像多余的分割线，且文案承诺了组件根本没有的能力
             （「可拖动排序或取消置顶」——首页 widget 既无拖拽也无取消置顶入口，
             用户按提示去找两个都找不到）。
             改为挂在区块标题的 info 图标上：需要时 hover 可读，不占版面、不抢视线。 -->
        <SectionHeader :title="watchlistTitle" :info="watchlistHint">
          <template #action>
            <div class="flex items-center gap-2">
              <el-button
                size="small"
                type="primary"
                plain
                @click="showAddWatchlistModal = true"
              >
                <template #icon><IconifyIconOffline icon="ep:plus" /></template
                >添加
              </el-button>
              <el-button
                size="small"
                link
                @click="$router.push('/the-road-not-taken')"
                >特别关注</el-button
              >
              <el-button size="small" link @click="$router.push('/watchlist')"
                >查看全部</el-button
              >
            </div>
          </template>
        </SectionHeader>
        <WatchlistWidget
          ref="watchlistWidgetRef"
          :key="watchlistWidgetKey"
          class="flex-1"
          @add="showAddWatchlistModal = true"
          @select="onWatchlistSelect"
        />
      </div>
    </div>

    <!-- ===== 第四排：财务晴雨表 + 心理账户（统一 12 列栅格 + 等宽右栏） ===== -->
    <WelcomeFinanceFeed
      :home-feed="homeFeed"
      :mental-accounts="mentalAccounts"
    />

    <!-- 添加自选弹窗 -->
    <AddToWatchlistModal
      v-model="showAddWatchlistModal"
      @submitted="onWatchlistChanged"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import WatchlistWidget from "@/components/WatchlistWidget/index.vue";
import type { HomeSummaryItem } from "@/api/types";
import { resolveDetailPath } from "@/utils/productDetailNav";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import PnlCalendar from "@/components/PnlCalendar/index.vue";
import WelcomeGreeting from "./components/WelcomeGreeting.vue";
import WelcomeAssetBoard from "./components/WelcomeAssetBoard.vue";
import WelcomeXirrTemperature from "./components/WelcomeXirrTemperature.vue";
import WelcomeFinanceFeed from "./components/WelcomeFinanceFeed.vue";
import { useWelcomeData } from "./composables/useWelcomeData";

defineOptions({
  name: "Welcome"
});

// 页面状态单体：欢迎语 / 播报 / 汇总 / XIRR / 温度 / 派生列表（#980 拆分）
const {
  summary,
  distributions,
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
  fetchDistributions,
  fetchXirr,
  fetchTemperature,
  fetchRecordStats,
  summaryError,
  xirrError,
  retryAssetLoad
} = useWelcomeData();

// 资产分布饼图：echarts 实例在 WelcomeAssetBoard 内，汇总数据就绪后经其 expose 的 render 首绘
const assetBoardRef = ref<InstanceType<typeof WelcomeAssetBoard> | null>(null);

// ===== 第三排（自选行）行内状态 =====
const showAddWatchlistModal = ref(false);
const watchlistWidgetKey = ref(0);
const watchlistWidgetRef = ref<InstanceType<typeof WatchlistWidget> | null>(
  null
);

// 动态标题
const watchlistTitle = computed(() => {
  if (!watchlistWidgetRef.value) return "自选资产";
  return watchlistWidgetRef.value.hasPinned ? "置顶资产" : "持仓市值最大资产";
});

/**
 * 区块指引文案（挂SectionHeader 的 info tooltip，#1954）。
 * 两种状态给的指引不同——有置顶时用户想的是「怎么取消/调顺序」，
 * 无置顶时想的是「怎么置顶」。直接由 widget 的 expose 派生，不另存状态。
 */
const watchlistHint = computed(() =>
  watchlistWidgetRef.value?.hasPinned
    ? "置顶的资产会固定排在最前。取消置顶、调整顺序请到「我的自选」页操作。"
    : "当前展示持仓市值最大的资产。在「我的自选」页点击图钉即可置顶，置顶后会固定显示在这里。"
);

// ===== 事件处理 =====
// 行点击 → 跳产品详情（#1965）：本页承接 WatchlistWidget 的 `select` 事件。
// #1954 曾摘掉这个挂载，因为当时详情页不存在、`onWatchlistSelect` 是个空函数 +
// `// TODO: 跳转到资产详情`——整行 cursor-pointer、行内按钮有 hover 反馈，点了却什么都不
// 发生，是「像 demo」的直接来源。现详情页已落地（路由 #1964 / 接线 #1965），按当时的
// 约定把它接回来，并且**不再是空函数**。
const router = useRouter();

const onWatchlistSelect = async (item: HomeSummaryItem) => {
  try {
    // 摘要行的 asset_type 可能为空、也没有 market → 内部回后端问权威品类，
    // 不在前端按 symbol 形态猜（那正是 #1497 错标成一堆无关基金的根因）
    const path = await resolveDetailPath({
      symbol: item.symbol,
      assetType: item.asset_type,
      venue: item.venue
    });
    if (!path) {
      ElMessage.warning("该品类详情页暂未开放");
      return;
    }
    await router.push(path);
  } catch {
    ElMessage.warning("未找到该产品，可能已下架或代码有误");
  }
};

const onWatchlistChanged = () => {
  watchlistWidgetKey.value++;
};

// 资产关键数据重试（#1832）：重拉汇总 + 年化。
// 饼图重绘不再需要显式调用——图表收敛到 AssetAllocationDonut 后（#1902），
// 组件自己 watch data 重绘，props 变化即触发。
const onRetryAsset = async () => {
  await retryAssetLoad();
};

// ===== 生命周期（顺序与拆分前一致：汇总 → 其余并行；ticker 清理在 composable 内） =====
onMounted(() => {
  fetchSummary();
  fetchDistributions();
  fetchXirr();
  fetchTemperature();
  fetchRecordStats();
  startTicker();
});
</script>

<style scoped>
@keyframes fade-up {
  from {
    opacity: 0;
    transform: translateY(24px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.welcome-container {
  font-family: var(
    --font-sans,
    "PingFang SC",
    "Hiragino Sans GB",
    "Microsoft YaHei",
    sans-serif
  );
}

/* 拆分说明（#980）：欢迎页模板已拆到 ./components/*，以下规则多数作用于
   子组件内部元素——子组件根节点会继承本页 scope id，但其内部节点不会，
   故跨子组件的规则统一用 :deep() 包裹（作用域仍限定在本页树内）；
   未迁出的第三排仍由本页模板直接渲染，:deep 同样覆盖。 */
:deep(.welcome-nickname) {
  padding: 0 8px;
  font-weight: 600;
  color: var(--text-primary);
  background: var(--brand-100);
  border-radius: 8px;
}

/* 顶部消息播报轮动过渡 */
:deep(.ticker-fade-enter-active),
:deep(.ticker-fade-leave-active) {
  transition:
    opacity 0.3s ease,
    transform 0.3s ease;
}

:deep(.ticker-fade-enter-from) {
  opacity: 0;
  transform: translateY(8px);
}

:deep(.ticker-fade-leave-to) {
  opacity: 0;
  transform: translateY(-8px);
}

:deep(.card-enter) {
  opacity: 0;
  animation: fade-up 0.6s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

:deep(.card-enter:nth-child(1)) {
  animation-delay: 0.05s;
}

:deep(.card-enter:nth-child(2)) {
  animation-delay: 0.1s;
}

:deep(.card-enter:nth-child(3)) {
  animation-delay: 0.15s;
}

:deep(.card-enter:nth-child(4)) {
  animation-delay: 0.2s;
}

:deep(.card-enter:nth-child(5)) {
  animation-delay: 0.25s;
}

:deep(.card-hover) {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

:deep(.card-hover:hover) {
  box-shadow: var(--shadow-float) !important;
}

:deep(.mental-account-item) {
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease;
}

:deep(.mental-account-item:hover) {
  background-color: var(--bg-hover);
  border-color: var(--border-default) !important;
}

:deep(.hover-card-btn) {
  transition:
    background-color 0.2s ease,
    color 0.2s ease,
    transform 0.2s ease;
}

:deep(.hover-card-btn:hover) {
  /* #1600：原 `--bg-card` 作文字——暗色下 --bg-card 为深色 #242120，在品牌实底上仅 3.43:1，
     且违反 design.dark.md「禁止使用 --bg-card 作按钮文字」的编码红线；改用 --text-inverse。 */
  color: var(--text-inverse) !important;
  background-color: var(--brand-solid) !important;
  transform: scale(1.05);
}

.text-hero {
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-weight: 600;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* 首页欢迎语 CTA（胶囊，CTA 例外；交互态遵循 design.md 主按钮规范） */
:deep(.btn-welcome-cta) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  padding: 8px 20px;
  font-size: 14px;
  font-weight: 500;
  line-height: 1;
  color: var(--text-inverse);
  white-space: nowrap;
  background-color: var(--brand-solid);
  border-radius: var(--radius-pill);
  transition:
    background-color 0.2s ease,
    transform 0.1s ease;
}

:deep(.btn-welcome-cta:hover) {
  background-color: var(--brand-solid-hover);
}

:deep(.btn-welcome-cta:active) {
  background-color: var(--brand-solid-active);
  transform: translateY(1px);
}

:deep(.btn-welcome-cta:focus-visible) {
  outline: none;
  box-shadow: var(--focus-ring);
}

/* ===== 短/中/长期温度行内三连（P3） ===== */
:deep(.temp-bands) {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  align-items: center;
  padding: 10px 12px;
  margin-top: 4px;
  background: var(--bg-soft);
  border-radius: 12px;
}

:deep(.temp-band) {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  font-size: 12px;
  line-height: 1.4;
}

:deep(.temp-band__label) {
  color: var(--text-secondary);
  white-space: nowrap;
}

:deep(.temp-band__value) {
  font-family: var(--font-mono, monospace);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

:deep(.temp-band__pill) {
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  border-radius: 999px;
}

/* B3: 综合温度环下方结论副文案 */
:deep(.temp-conclusion) {
  padding: 8px 12px;
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: 10px;
}

/* 欢迎语昵称：暖色背景 chip 表达「这位用户对我们很特别、被关心」。
   文字保持主色、不用红色——避讳人名用红色（关联墓碑/断交等不吉意味）。 */

/* 与之前一致，保持不变 */
</style>
