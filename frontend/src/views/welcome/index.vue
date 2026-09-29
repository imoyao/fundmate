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
    <WelcomeAssetBoard ref="assetBoardRef" :summary="summary" />

    <!-- ===== 第二排：年化收益追踪 + 市场温度（同一层级） ===== -->
    <WelcomeXirrTemperature
      v-model:includeCashEquivalents="includeCashEquivalents"
      :portfolio-xirr="portfolioXirr"
      :composite-temperature="compositeTemperature"
      :temperature-bands="temperatureBands"
      :temperature-conclusion="temperatureConclusion"
      :band-pill-style="bandPillStyle"
      @change="fetchXirr"
    />

    <!-- ===== 第三排：持仓市值最大资产 ===== -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-8">
      <!-- 持仓市值最大资产（风险预警改由顶部消息播报承载，本页不再保留静态风险热力图） -->
      <div
        class="lg:col-span-12 flex flex-col gap-3 card-hover card-enter h-full"
      >
        <SectionHeader :title="watchlistTitle">
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
          @select="onWatchlistSelect"
          @add="showAddWatchlistModal = true"
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
import { type HomeSummaryItem } from "@/api/watchlist";
import WatchlistWidget from "@/components/WatchlistWidget.vue";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
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
  fetchRecordStats
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

// ===== 事件处理 =====
const onWatchlistSelect = (item: HomeSummaryItem) => {
  // TODO: 跳转到资产详情
};

const onWatchlistChanged = () => {
  watchlistWidgetKey.value++;
};

// ===== 生命周期（顺序与拆分前一致：汇总 → 其余并行；ticker 清理在 composable 内） =====
onMounted(() => {
  fetchSummary().then(() => nextTick(() => assetBoardRef.value?.render()));
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
