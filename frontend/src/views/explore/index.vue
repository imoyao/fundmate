<!-- frontend/src/views/explore/index.vue -->
<!--
  探市页（免登录沙盒，站点唯一市场入口，D4）。

  方案 D（2026-09-12）：原独立温度计页收敛为本页「深度」档，页内以胶囊 Tab 切换
  「概览 / 深度」，档位与 ?view= 查询参数双向同步。

  本文件**只做编排**（#980）：数据与列表行为收口在 useExploreWatchlist，
  温度数据收口在 useTemperatureOverview（单例），核心指标清单收口在 useCoreMetrics。
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

    <!-- ===== 档位切换（分组胶囊 Tab，design.md 规范） ===== -->
    <nav class="panel-switch" aria-label="探市视图切换">
      <div class="panel-switch__inner">
        <button
          v-for="tab in panelTabs"
          :key="tab.key"
          type="button"
          class="panel-tab"
          :class="{ 'panel-tab--active': activePanel === tab.key }"
          @click="switchPanel(tab.key)"
        >
          {{ tab.label }}
        </button>
        <span class="panel-switch__hint">{{ activeHint }}</span>
      </div>
    </nav>

    <!-- ============================================================ -->
    <!-- 概览档：温度锚点 + 指数快照 + 观察列表（漏斗主体）            -->
    <!-- ============================================================ -->
    <!-- 常驻渲染：切档只切显示（v-show），不卸载重挂 —— 两档的 onMounted 都会取数，用 v-if 会让每次切档都重打一遍接口 -->
    <div v-show="activePanel === 'overview'">
      <ExploreTemperatureDashboard @go-detail="switchPanel('detail')" />

      <!-- ============================================================ -->
      <!-- 大类资产观察（#1436 / #1444 收口实现：新增区块，紧跟温度仪表盘） -->
      <!-- ============================================================ -->
      <ExploreAssetOverview />

      <!-- 添加/观察栏（仅未登录渲染） -->
      <ExploreAddSection
        v-if="!isAuthenticated"
        id="add-section"
        :add-holding="addHolding"
        :quotes-map="quotesMap"
      />

      <!-- 匿名用户转化区（#822 todo1）：注册 CTA / 损失厌恶文案 -->
      <section v-if="!isAuthenticated" class="conv-banner">
        <div class="conv-banner__inner">
          <div class="conv-banner__text">
            <div class="conv-banner__title">免费注册，解锁完整投资账本</div>
            <div class="conv-banner__desc">
              注册后观察列表跨设备同步，并可在自选页管理分组、标签与 AI
              批量导入——当前为本地临时观察，清除浏览器数据会丢失。
            </div>
          </div>
          <el-button type="primary" @click="goToLogin">
            立即注册 / 登录
            <IconifyIconOffline icon="ep:arrow-right" class="ml-1" />
          </el-button>
        </div>
      </section>

      <!-- 已登录：引导去自选页（探市只做展示与观察，管理能力收敛到登录后的自选） -->
      <section v-if="isAuthenticated" class="auth-guide">
        <div class="auth-guide__inner">
          <div class="auth-guide__text">
            <div class="auth-guide__title">已登录，可前往自选页管理资产</div>
            <div class="auth-guide__desc">
              探市页仅用于浏览市场数据；分组、标签、AI
              批量导入等功能已迁移至自选页统一管理。
            </div>
          </div>
          <el-button type="primary" @click="goToWatchlist">
            前往自选页
            <IconifyIconOffline icon="ep:arrow-right" class="ml-1" />
          </el-button>
        </div>
      </section>

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
    </div>

    <!-- ============================================================ -->
    <!-- 深度档：完整温度画像（由原温度计页迁移而来）                  -->
    <!-- ============================================================ -->
    <!-- 首次进入才挂载（其 onMounted 会打 4 个接口），此后常驻只切显示 -->
    <ExploreDetailPanel
      v-if="detailMounted"
      v-show="activePanel === 'detail'"
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
      copyright="© 2026 多多贝 · 让投资更从容"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import MarketHeader from "@/components/MarketHeader/index.vue";
import PageFooter from "@/components/PageFooter/index.vue";
import {
  MARKET_LOGO,
  useMarketHeaderNavs
} from "@/components/MarketHeader/config";
import { buildMarketFooterSources } from "@/components/MarketFooter/config";
import { useAuthState } from "@/composables/useAuthState";
import { useTemperatureOverview } from "@/composables/temperature/useTemperatureOverview";
import ExploreTemperatureDashboard from "./components/ExploreTemperatureDashboard.vue";
import ExploreAssetOverview from "./components/ExploreAssetOverview.vue";
import ExploreDetailPanel from "./components/ExploreDetailPanel.vue";
import { useExploreWatchlist } from "./composables/useExploreWatchlist";

defineOptions({
  name: "ExplorePage"
});

// 登录态感知（探市免登录页，D4）
const { isAuthenticated } = useAuthState();

const route = useRoute();
const router = useRouter();

// ================================================================
// 档位切换：概览 / 深度，与 ?view= 查询参数双向同步
// ================================================================
type PanelKey = "overview" | "detail";

const panelTabs: Array<{ key: PanelKey; label: string }> = [
  { key: "overview", label: "概览" },
  { key: "detail", label: "深度" }
];

const PANEL_HINTS: Record<PanelKey, string> = {
  overview: "一屏看懂市场冷热，并建立自己的观察列表",
  detail: "行业维度、趋势与全部指标明细"
};

const normalizePanel = (raw: unknown): PanelKey =>
  raw === "detail" ? "detail" : "overview";

const activePanel = ref<PanelKey>(normalizePanel(route.query.view));
const activeHint = computed(() => PANEL_HINTS[activePanel.value]);

// URL 变化（含 /temperature 重定向过来、浏览器前进后退）时同步档位
watch(
  () => route.query.view,
  raw => {
    activePanel.value = normalizePanel(raw);
  }
);

const switchPanel = (key: PanelKey) => {
  activePanel.value = key;
  // replace 而非 push：切换档位不应污染历史栈，避免返回键在档位间循环
  router.replace({
    path: "/explore",
    query: key === "detail" ? { view: "detail" } : {}
  });
};

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
watch(activePanel, val => {
  if (val === "detail") detailMounted.value = true;
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
const { links } = useTemperatureOverview();
const footerSources = computed(() => buildMarketFooterSources(links.value));

// ================================================================
// 页面导航（页面编排职责，留在页面内）
// ================================================================
const goToWatchlist = () => {
  router.push("/watchlist");
};

const goToLogin = () => {
  router.push("/login");
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

/* ============================================================
   档位切换：分组胶囊 Tab（design.md「分组胶囊 Tab」规范）
   选中态 = 软按钮语义（brand 底 + brand 字），非涨跌色
   ============================================================ */
.panel-switch {
  max-width: 1280px;
  padding: var(--space-standard) 24px 0;
  margin: 0 auto;

  &__inner {
    display: flex;
    gap: 8px;
    align-items: center;
    padding-bottom: 12px;
    overflow-x: auto;
    border-bottom: 1px solid var(--border-subtle);
  }

  &__hint {
    margin-left: auto;
    font-size: 12px;
    color: var(--text-tertiary);
    white-space: nowrap;
  }
}

.panel-tab {
  flex-shrink: 0;
  height: 32px;
  padding: 0 16px;
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;

  &:hover {
    background: var(--bg-hover);
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }

  &--active {
    color: var(--brand-700);
    background: var(--brand-100);
    border-color: var(--brand-400);

    &:hover {
      background: var(--brand-200);
    }
  }
}

@media (width <= 768px) {
  .panel-switch {
    padding: 16px 16px 0;

    &__hint {
      display: none;
    }
  }
}

/* ============================================================
   匿名用户注册转化区（#822 todo1）
   ============================================================ */
.conv-banner {
  max-width: 1280px;
  padding: 0 24px 16px;
  margin: 0 auto;

  &__inner {
    display: flex;
    gap: 20px;
    align-items: center;
    justify-content: space-between;
    padding: 18px 24px;
    background: linear-gradient(135deg, var(--brand-50), var(--bg-card));
    border: 1px solid var(--brand-400);
    border-radius: 12px;
    box-shadow: var(--shadow-raised);
  }

  &__title {
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__desc {
    max-width: 860px;
    margin-top: 4px;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-secondary);
  }
}

/* ============================================================
   已登录引导区
   ============================================================ */
.auth-guide {
  max-width: 1280px;
  padding: 0 24px 16px;
  margin: 0 auto;

  &__inner {
    display: flex;
    gap: 20px;
    align-items: center;
    justify-content: space-between;
    padding: 18px 24px;
    background: var(--bg-card);
    border: 1px solid var(--border-light);
    border-radius: 12px;
    box-shadow: var(--shadow-raised);
  }

  &__title {
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__desc {
    max-width: 860px;
    margin-top: 4px;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-secondary);
  }
}
</style>
