<!-- frontend/src/views/explore/components/ExploreDetailPanel.vue -->
<!--
  探市「深度」档（方案 D，2026-09-12）：由原温度计页面整体迁移而来。
  header / footer / 未登录引导条已剥离（由父页面 views/explore/index.vue 统一提供）。

  2026-09-12 按 #980 拆分：核心指标清单收口到 useCoreMetrics、
  趋势图抽为 TemperatureTrendChart，本文件只做区域编排。

  2026-10 再拆（#980 续）：上半屏（仪表盘 + 温度解读 + 市场机会）→ detail/ExploreDashboardSection，
  行业/赛道排行 → detail/ExploreRankSection（含三张表的数据层 useRankTables）。
  本文件只剩「区块顺序」与数据新鲜度守卫。
-->
<template>
  <div class="detail-panel">
    <!-- 数据新鲜度守卫（#1431）：最新数据超阈值未更新时显式提示，不静默展示旧值 -->
    <div v-if="freshness?.stale" class="freshness-alert" role="alert">
      <IconifyIconOffline icon="ep:warning" class="freshness-alert__icon" />
      <span class="freshness-alert__text">
        当前展示的是 {{ freshness.latest || "更早" }} 的市场数据（距今约
        {{ freshness.age_days }} 天，已超过 {{ freshness.threshold_days }}
        天阈值），数据源可能暂不可用，请谨慎参考。
      </span>
    </div>

    <!-- 综合仪表盘 + 温度解读 + 市场机会 -->
    <ExploreDashboardSection :gauge-visible="gaugeVisible" />

    <!-- 综合温度趋势（自带标题栏、周期切换与取数） -->
    <TemperatureTrendChart />

    <!-- 行业 / 赛道排行（含紧随其后的拥挤度趋势图，两处共用 rankCategory） -->
    <ExploreRankSection />

    <!-- 行业 PB-ROE 散点（#2481）：韭圈儿免登录源日频快照，读库即回。
         负 ROE 行业在 PB-ROE 模型下有效（x 轴 scale 不裁负值 + ROE=0 参考线）；
         无快照（job 失败日）显示「暂无数据」提示，不影响其它区块。 -->
    <IndustryPbroeScatter />

    <!-- 全部市场温度指标：紧凑表格 -->
    <MetricDetailTable :items="detailMetrics" />

    <!-- 大类资产观察（#1671 方案 b：由概览档迁入本档）
         外层锚点供概览档入口滚动定位；scroll-margin-top 让定位后不被顶部压住 -->
    <div id="asset-overview-anchor" class="asset-overview-anchor">
      <ExploreAssetOverview :default-expanded="assetExpanded" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { useTemperatureOverview } from "@/composables/temperature/useTemperatureOverview";
import { CORE_SINGLE_SOURCES } from "@/constants/temperature";
import TemperatureTrendChart from "./TemperatureTrendChart.vue";
import IndustryPbroeScatter from "./IndustryPbroeScatter.vue";
import ExploreAssetOverview from "./ExploreAssetOverview.vue";
import MetricDetailTable from "./detail/MetricDetailTable.vue";
import ExploreDashboardSection from "./detail/ExploreDashboardSection.vue";
import ExploreRankSection from "./detail/ExploreRankSection.vue";

defineOptions({
  name: "ExploreDetailPanel"
});

withDefaults(
  defineProps<{
    gaugeVisible?: boolean;
    /**
     * 大类资产观察是否默认展开（#1671 方案 b）。
     * 用户从概览档入口跳来时为 true —— 直接展示数据，避免「跳过来还得再点一次展开」；
     * 自然逛进深度档时保持 false，不白白触发那个冷缓存很慢的接口。
     */
    assetExpanded?: boolean;
  }>(),
  { gaugeVisible: true, assetExpanded: false }
);

// ================================================================
// 市场温度总览：与概览档共享同一份数据实例（单例 + 并发去重，见该 composable 头注释）
// 仪表盘与温度解读在 ExploreDashboardSection 里自行取同一实例，这里只用 freshness。
// ================================================================
const { overview, freshness, fetchTemperature } = useTemperatureOverview();

// 全部单值指标（过滤核心指标，按数据分层展示）
const detailMetrics = computed(() => {
  const singles = overview.value?.singles || [];
  return singles.filter((s: any) => !CORE_SINGLE_SOURCES.includes(s.source));
});

// ================================================================
// 生命周期
// ================================================================
onMounted(() => {
  // #1546 T2.1：并发取数。排行三张表在 ExploreRankSection 的 onMounted 里一起发起
  // （子组件先于父组件挂载完成），四个请求仍是同轮并发，不会退化成串行。
  void fetchTemperature();
});
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* 数据新鲜度守卫横幅（#1431）：沿用「数据滞后」pill 的警示色视觉语言 */
.freshness-alert {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 35%, transparent);
  border-radius: 8px;
}

.freshness-alert__icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.freshness-alert__text {
  flex: 1;
}

/* 深度档容器：与概览档共用同一套页面边距与最大宽度 */
.detail-panel {
  max-width: var(--layout-content-width);
  padding: var(--space-standard) 24px 16px;
  margin: 0 auto;

  /* 窄屏收内边距。
     ⚠️ 本块必须留在基础声明**之后**：`@include` 的编译产物就是媒体查询，而媒体查询不改变
     特异性——写在 `padding` 之前会被它压掉。2026-09-18 之前本块正是排在前面
     （条件是「768px 及以下」的裸查询），于是窄屏始终是 24px 侧边距，从未生效
     （同族缺陷见 #1576 / #1557：源序即语义）。 */
  @include bp.below("md") {
    padding: 16px;
  }
}

/* 大类资产观察锚点（#1671 方案 b）：概览档入口跳转后的滚动定位目标 */
.asset-overview-anchor {
  scroll-margin-top: 16px;
}
</style>
