<!-- frontend/src/views/explore/index.vue -->
<!--
  探市页（免登录沙盒，站点唯一市场入口，D4）。

  方案 D（2026-09-12）：原独立温度计页收敛为本页「深度」档，页内以胶囊 Tab 切换
  「概览 / 深度 / 行业情绪」，档位与 ?view= 查询参数双向同步。

  本文件**只做编排**（#980）：档位切换收口在 usePanelSwitch，数据与列表行为收口在
  useExploreWatchlist，温度数据收口在 useTemperatureOverview（单例），
  三块提示卡片（转化区 / 已登录引导 / 大类资产入口）拆成 exploreView/ 下的片段组件。
-->
<template>
  <div class="explore-page">
    <!-- ===== 顶部导航（公共组件） ===== -->
    <MarketHeader
      :logo="MARKET_LOGO"
      badge="探市"
      :navs="headerNavs"
      @logo-click="onLogoClick"
    />

    <!-- 页面统一页头（PageHeaderBar）：H1 + 副标题 + 数据更新时间胶囊。
         更新时间与「综合温度」卡同源（temperature/overview 的 updated_at），不另取一份。 -->
    <PageHeaderBar
      title="探市"
      subtitle="汇总市场温度、行业冷热与指数快照，辅助判断当前的布局方向"
      :updated-at="headerUpdatedAt"
    />

    <!-- ===== 档位切换（分组胶囊 Tab，design.md 规范） ===== -->
    <ExplorePanelSwitch :active-panel="activePanel" @switch="switchPanel" />

    <!-- ============================================================ -->
    <!-- 概览档：温度锚点 + 指数快照 + 观察列表（漏斗主体）            -->
    <!-- ============================================================ -->
    <!-- 常驻渲染：切档只切显示（v-show），不卸载重挂 —— 两档的 onMounted 都会取数，用 v-if 会让每次切档都重打一遍接口 -->
    <div
      v-show="activePanel === 'overview'"
      id="panel-overview"
      role="tabpanel"
      aria-labelledby="panel-tab-overview"
    >
      <ExploreTemperatureDashboard
        :gauge-visible="activePanel === 'overview'"
        @go-detail="switchPanel('detail')"
      />

      <!-- 添加/观察栏（仅未登录渲染） -->
      <ExploreAddSection
        v-if="!isAuthenticated"
        id="add-section"
        :add-holding="addHolding"
        :quotes-map="quotesMap"
      />

      <ExploreWatchlistTable
        :rows="tableData"
        :loading="loading"
        :total-count="totalCount"
        :is-pure-observation-mode="isPureObservationMode"
        :summary="summary"
        :status-class="statusClass"
        :status-text="statusText"
        :refresh-interval="refreshInterval"
        :last-update-time="lastUpdateTime"
        @remove="handleRemove"
        @jump="handleJump"
        @favorite="handleFavorite"
        @refresh="manualRefresh"
        @interval-change="setRefreshInterval"
      />

      <!-- 匿名用户转化区（#822 todo1）：注册 CTA / 损失厌恶文案 -->
      <!-- #1546 T2.2：位置从「观察列表之前」移到之后——访客先看目的内容，再看注册转化 -->
      <ExploreConvBanner v-if="!isAuthenticated" @login="goToLogin" />

      <!-- 已登录：引导去自选页（探市只做展示与观察，管理能力收敛到登录后的自选） -->
      <!-- 可关闭且关闭后永久生效（localStorage）——避免常驻提示反复打扰 -->
      <ExploreAuthGuide
        v-if="isAuthenticated && !authGuideDismissed"
        @watchlist="goToWatchlist"
        @dismiss="dismissAuthGuide"
      />

      <!-- ============================================================ -->
      <!-- 大类资产观察入口（#1671 方案 b，决策见该 issue）                -->
      <!-- 区块本体已移入「深度」档，概览档只留这一行轻量入口：            -->
      <!-- 既让概览档聚焦（温度锚点 + 观察列表），又不丢这个能力的发现性。 -->
      <!-- 点击后切到深度档、滚动定位到该区块，并直接以展开态渲染。        -->
      <!-- ============================================================ -->
      <ExploreAssetEntry @open="goAssetOverview" />
    </div>

    <!-- ============================================================ -->
    <!-- 深度档：完整温度画像（由原温度计页迁移而来）                  -->
    <!-- ============================================================ -->
    <!-- 首次进入才挂载（其 onMounted 会打 4 个接口），此后常驻只切显示 -->
    <ExploreDetailPanel
      v-if="detailMounted"
      v-show="activePanel === 'detail'"
      id="panel-detail"
      role="tabpanel"
      aria-labelledby="panel-tab-detail"
      :gauge-visible="activePanel === 'detail'"
      :asset-expanded="assetAutoExpand"
    />

    <!-- ============================================================ -->
    <!-- 行业情绪档：韭圈儿行业恐贪快照（#2479，与深度档平级）          -->
    <!-- ============================================================ -->
    <ExploreIndustryEmotionPanel
      v-if="emotionMounted"
      v-show="activePanel === 'emotion'"
      id="panel-emotion"
      role="tabpanel"
      aria-labelledby="panel-tab-emotion"
    />

    <!-- ============================================================ -->
    <!-- 底部（公共组件）：数据来源 + 免责声明                         -->
    <!-- ============================================================ -->
    <PageFooter
      revisit-text="探市页汇总市场温度、行业冷热与指数快照，辅助判断布局方向，不构成投资建议。"
      :revisit-items="[
        '回看温度与行业冷热的计算口径',
        '把当前市场冷热记录下来，做纵向对比',
        '关注公众号获取更多市场监测解读'
      ]"
      :sources="footerSources"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useLocalStorage } from "@vueuse/core";
import MarketHeader from "@/components/MarketHeader/index.vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageFooter from "@/components/PageFooter/index.vue";
import {
  MARKET_LOGO,
  useMarketHeaderNavs
} from "@/components/MarketHeader/config";
import { buildMarketFooterSources } from "@/components/MarketFooter/config";
import { useAuthState } from "@/composables/useAuthState";
import { useTemperatureOverview } from "@/composables/temperature/useTemperatureOverview";
import ExploreTemperatureDashboard from "./components/ExploreTemperatureDashboard.vue";
import ExploreDetailPanel from "./components/ExploreDetailPanel.vue";
import ExploreIndustryEmotionPanel from "./components/ExploreIndustryEmotionPanel.vue";
import { useExploreWatchlist } from "./composables/useExploreWatchlist";
import { usePanelSwitch } from "./exploreView/usePanelSwitch";
import ExplorePanelSwitch from "./exploreView/ExplorePanelSwitch.vue";
import ExploreConvBanner from "./exploreView/ExploreConvBanner.vue";
import ExploreAuthGuide from "./exploreView/ExploreAuthGuide.vue";
import ExploreAssetEntry from "./exploreView/ExploreAssetEntry.vue";

defineOptions({
  name: "ExplorePage"
});

// 登录态感知（探市免登录页，D4）
const { isAuthenticated } = useAuthState();

/**
 * 登录后引导条（「已登录，可前往自选页管理资产」）可手动关闭，关闭后永久生效。
 * 用 localStorage 持久化；key 带版本号——将来文案/引导目标改版时递增 v2，
 * 老用户的关闭状态自然失效，会重新看到一次新提示。
 */
const AUTH_GUIDE_DISMISS_KEY = "explore:auth-guide-dismissed:v1";
const authGuideDismissed = useLocalStorage<boolean>(
  AUTH_GUIDE_DISMISS_KEY,
  false
);
const dismissAuthGuide = () => {
  authGuideDismissed.value = true;
};

const route = useRoute();
const router = useRouter();

// ================================================================
// 档位切换：概览 / 深度 / 行业情绪，与 ?view= 查询参数双向同步（见 usePanelSwitch）
// ================================================================
const { activePanel, switchPanel } = usePanelSwitch({ route, router });

/**
 * 档位内容「常驻」策略（见 #980「页面只做编排、数据不重复取」）：
 * 切档只切显示、不卸载组件 —— 两档的 onMounted 各自取数
 * （概览档：温度总览 + 大类资产；深度档：温度总览 + 乖离率 + 拥挤度 + 趋势），
 * 若用 v-if 卸载重挂，每次切档都会把接口重打一遍。
 *
 * 深度档额外用 detailMounted 做「首次进入才挂载」：它的取数更重，
 * 用户从不进深度档就不该产生这批请求；概览档是首屏，直接常驻。
 */
const detailMounted = ref(activePanel.value === "detail");

/**
 * 「行业情绪」档同样用懒挂载（emotionMounted）：它只打一个轻量端点，但用户从不进
 * 该档就不该产生这次请求；首次进入才挂载、之后常驻只切显示（v-show）。
 */
const emotionMounted = ref(activePanel.value === "emotion");

watch(activePanel, val => {
  if (val === "detail") detailMounted.value = true;
  if (val === "emotion") emotionMounted.value = true;
});

// ================================================================
// 观察列表：数据与行为收口在 composable（见 #980 第三步）
// ================================================================
const {
  addHolding,
  quotesMap,
  tableData,
  loading,
  totalCount,
  isPureObservationMode,
  summary,
  statusClass,
  statusText,
  refreshInterval,
  lastUpdateTime,
  setRefreshInterval,
  manualRefresh,
  startRealtime,
  handleRemove,
  handleJump,
  handleFavorite
} = useExploreWatchlist(router);

// ================================================================
// Header / Footer 公共组件数据
// ================================================================
const headerNavs = useMarketHeaderNavs();

// 来源链接直接取温度 composable（单例）：不依赖概览档组件的挂载状态，
// 切到深度档时 footer 来源条不会因组件卸载而变空。
const { overview, links } = useTemperatureOverview();
const footerSources = computed(() => buildMarketFooterSources(links.value));

// 页头「更新时间」胶囊：与「综合温度」卡同源（temperature/overview 的 updated_at），
// 后端格式为 "YYYY-MM-DD HH:MM:SS"；后缀「更新」沿用 PageHeaderBar 的 prop 约定。
const headerUpdatedAt = computed(() =>
  overview.value?.updated_at ? `${overview.value.updated_at} 更新` : ""
);

// ================================================================
// 页面导航（页面编排职责，留在页面内）
// ================================================================
const goToWatchlist = () => {
  router.push("/watchlist");
};

const goToLogin = () => {
  router.push("/login");
};

/**
 * 概览档「大类资产观察」入口（#1671 方案 b）：切到深度档并滚动定位到该区块。
 *
 * 深度档是「首次进入才挂载」（detailMounted），挂载可能晚一帧——所以先 nextTick
 * 再补一个 requestAnimationFrame，两次都调幂等的 scrollIntoView，避免首次点击时
 * 因 DOM 尚未挂载而定位落空。assetAutoExpand 让区块直接以展开态渲染，省掉
 * 「跳过来还得再点一次展开」。
 */
const assetAutoExpand = ref(false);
const goAssetOverview = () => {
  assetAutoExpand.value = true;
  switchPanel("detail");
  const scrollToAsset = () => {
    document.getElementById("asset-overview-anchor")?.scrollIntoView({
      behavior: "smooth",
      block: "start"
    });
  };
  nextTick(() => {
    scrollToAsset();
    requestAnimationFrame(scrollToAsset);
  });
};

// logo 点击：登录态感知路由（#822 todo3）
// 已登录 → 工作台 /welcome；未登录 → 探市首页 /explore
const onLogoClick = () => {
  router.push(isAuthenticated.value ? "/welcome" : "/explore");
};

// ================================================================
// 生命周期
// ================================================================
onMounted(startRealtime);
</script>

<style lang="scss" scoped>
.explore-page {
  min-height: 100vh;
  background: var(--bg-page);
}
</style>
