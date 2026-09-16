<!-- frontend/src/views/explore/components/ExploreDetailPanel.vue -->
<!--
  探市「深度」档（方案 D，2026-09-12）：由原温度计页面整体迁移而来。
  header / footer / 未登录引导条已剥离（由父页面 views/explore/index.vue 统一提供）。

  2026-09-12 按 #980 拆分：核心指标清单收口到 useCoreMetrics、
  趋势图抽为 TemperatureTrendChart，本文件只做区域编排。
-->
<template>
  <div v-loading="loading" class="detail-panel">
    <!-- 数据新鲜度守卫（#1431）：最新数据超阈值未更新时显式提示，不静默展示旧值 -->
    <div v-if="freshness?.stale" class="freshness-alert" role="alert">
      <IconifyIconOffline icon="ep:warning" class="freshness-alert__icon" />
      <span class="freshness-alert__text">
        当前展示的是 {{ freshness.latest || "更早" }} 的市场数据（距今约
        {{ freshness.age_days }} 天，已超过 {{ freshness.threshold_days }}
        天阈值），数据源可能暂不可用，请谨慎参考。
      </span>
    </div>

    <!-- 综合仪表盘 -->
    <section class="dashboard-section">
      <MetricGrid>
        <!-- 综合温度仪表（大）——与概览档同源同貌；gaugeVisible 保证同一时刻
             全页只有一份仪表盘在 DOM 中（#1549 T4.1，参数由 index.vue 按档位传入） -->
        <TemperatureGaugeCard
          v-if="gaugeVisible"
          :value="compositeValue"
          title="综合市场温度"
          :level="compositeLevel"
          caption="基于多源市场数据计算"
          :updated-at="updatedAt"
          size="lg"
          featured
        />

        <!-- 核心指标（恐惧贪婪 / 股债性价比 / 可转债 / 成交额）：清单见 useCoreMetrics -->
        <MetricCard
          v-for="metric in coreMetrics"
          :key="metric.key"
          :title="metric.title"
          :value="metric.value"
          :unit="metric.unit"
          :level="metric.level"
        />
      </MetricGrid>
    </section>

    <!-- 温度解读 + 市场机会：与仪表卡配套，放在趋势图上方 -->
    <section class="context-section">
      <div class="context-grid">
        <TemperatureContextCard
          :temperature="compositeValue"
          :fear-greed="fearGreedValue"
          :fear-greed-label="fearGreedLabel"
          :periods="tempPeriods"
          caption="综合 6 个市场指标与市场情绪推导"
          class="context-card"
        />

        <!-- 市场机会（来自 temperature store，由综合温度与股债性价比推导） -->
        <div v-if="tempStore.opportunityList.length" class="opportunity-card">
          <SectionHeader title="市场机会" />
          <div class="opportunity-list">
            <div
              v-for="op in tempStore.opportunityList"
              :key="op.name"
              class="opportunity-item"
              :class="`opportunity-item--${op.tone}`"
            >
              <div class="opportunity-head">
                <span class="opportunity-name">{{ op.name }}</span>
                <span class="opportunity-tag">{{
                  op.tone === "safe"
                    ? "机会"
                    : op.tone === "danger"
                      ? "风险"
                      : "中性"
                }}</span>
              </div>
              <p class="opportunity-desc">{{ op.desc }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 综合温度趋势（自带标题栏、周期切换与取数） -->
    <TemperatureTrendChart />

    <!-- 行业 / 赛道排行（#1431）：单一卡片承载
         一级分类（申万行业 / 热门赛道）× 二级视图（拥挤度 / 乖离率），
         避免多张大表纵向堆叠；赛道维度无乖离率，切换分类时自动回到拥挤度 -->
    <CardBlock class="industry-rank-section">
      <SectionHeader title="行业 / 赛道排行" :info="activeRankView.info">
        <template #action>
          <div class="rank-switch" role="tablist" aria-label="排行分类切换">
            <button
              v-for="cat in RANK_CATEGORIES"
              :key="cat.key"
              type="button"
              role="tab"
              class="rank-switch__item"
              :class="{ 'rank-switch__item--active': rankCategory === cat.key }"
              :aria-selected="rankCategory === cat.key"
              @click="switchCategory(cat.key)"
            >
              {{ cat.label }}
            </button>
          </div>
          <div class="rank-switch" role="tablist" aria-label="排行视图切换">
            <button
              v-for="view in availableRankViews"
              :key="view.key"
              type="button"
              role="tab"
              class="rank-switch__item"
              :class="{ 'rank-switch__item--active': rankView === view.key }"
              :aria-selected="rankView === view.key"
              @click="rankView = view.key"
            >
              {{ view.label }}
            </button>
          </div>
          <span class="rank-updated"
            >更新：{{ activeRankView.date || "暂无" }}</span
          >
          <el-tooltip
            v-if="activeRankView.stale"
            :content="activeRankView.staleTip"
            placement="top"
          >
            <span class="rank-stale-pill">数据滞后</span>
          </el-tooltip>
        </template>
      </SectionHeader>

      <!-- 数据来源提示（外部临时源 / 已自动降级）：只提示、不报错（#1431 决策） -->
      <div
        v-if="sourceNotice"
        class="rank-source-notice"
        :class="`rank-source-notice--${sourceNotice.tone}`"
        role="status"
      >
        <IconifyIconOffline
          :icon="sourceNotice.icon"
          class="rank-source-notice__icon"
        />
        <span class="rank-source-notice__text">{{ sourceNotice.text }}</span>
      </div>

      <!-- 分位色标图例：提升表格可读性（配色仍用本站温度语义色，不引入外部色板） -->
      <div class="rank-legend">
        <span
          v-for="item in RANK_LEGEND"
          :key="item.label"
          class="rank-legend__item"
        >
          <i class="rank-legend__dot" :class="item.dotClass" />{{ item.label }}
        </span>
      </div>

      <CrowdingTable
        v-show="rankView === 'crowding'"
        embedded
        :items="activeCrowdingItems"
        :loading="activeCrowdingLoading"
        :name-column-label="rankCategory === 'track' ? '赛道' : '行业'"
      />
      <BiasTable
        v-if="rankCategory === 'sw'"
        v-show="rankView === 'bias'"
        embedded
        :items="biasItems"
        :loading="biasLoading"
      />
    </CardBlock>

    <!-- 拥挤度趋势（周度 / 月度；随上方分类联动「申万行业 / 热门赛道」） -->
    <IndustryCrowdingTrend :category="rankCategory" />

    <!-- 全部市场温度指标：紧凑表格 -->
    <MetricDetailTable :items="detailMetrics" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { getMultiItems } from "@/api/temperature";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import TemperatureContextCard from "@/components/TemperatureContextCard/index.vue";
import { useTemperatureStore } from "@/store/modules/temperature";
import { useTemperatureOverview } from "@/composables/temperature/useTemperatureOverview";
import { useCoreMetrics } from "@/composables/temperature/useCoreMetrics";
import {
  CORE_SINGLE_SOURCES,
  CROWDING_HIGH_THRESHOLD,
  CROWDING_LOW_THRESHOLD
} from "@/constants/temperature";
import TemperatureTrendChart from "./TemperatureTrendChart.vue";
import IndustryCrowdingTrend from "./IndustryCrowdingTrend.vue";
import BiasTable from "./detail/BiasTable.vue";
import CrowdingTable from "./detail/CrowdingTable.vue";
import MetricDetailTable from "./detail/MetricDetailTable.vue";

defineOptions({
  name: "ExploreDetailPanel"
});

/**
 * 是否渲染「综合温度」仪表盘（本组件其余区块不受影响）。
 * 父页面按当前档位传入：深度档显示时 true、概览档 false ——
 * 概览档已有一份同源同貌的温度计卡，两份同时留在 DOM 中属重复（#1549 T4.1）。
 * 仪表卡自身不取数（数据来自单例 composable），卸载重挂不会多打接口。
 */
withDefaults(
  defineProps<{
    gaugeVisible?: boolean;
  }>(),
  { gaugeVisible: true }
);

// ================================================================
// 市场温度总览：与概览档共享同一份数据实例（单例 + 并发去重，见该 composable 头注释）
// ================================================================
const {
  loading,
  overview,
  compositeTemperature,
  freshness,
  fearData,
  fetchTemperature
} = useTemperatureOverview();

// 核心指标清单收口在 useCoreMetrics（见 #980）
const { coreMetrics } = useCoreMetrics();

// ================================================================
// 页面独立数据：多指标接口（composable 未覆盖）
// ================================================================
const biasItems = ref<any[]>([]);
const biasDate = ref<string>("");
const biasStale = ref(false);
const biasLoading = ref(false);

// 行业拥挤度（独立维度：行业 PB / 全A 中位 PB 历史百分位）
const crowdingItems = ref<any[]>([]);
const crowdingDate = ref<string>("");
const crowdingStale = ref(false);
const crowdingLoading = ref(false);

// 热门赛道拥挤度（外部临时源 category=track，18 条；该维度无行业乖离率）
const trackItems = ref<any[]>([]);
const trackDate = ref<string>("");
const trackStale = ref(false);
const trackLoading = ref(false);

// ================================================================
// 行业 / 赛道排行（#1431）：一级分类（申万行业 / 热门赛道）+ 二级视图（拥挤度 / 乖离率）
// 赛道维度由外部临时源提供（category=track，18 条），无行业乖离率视图
// ================================================================
const RANK_CATEGORIES = [
  { key: "sw", label: "申万行业", source: "industry_crowding" },
  { key: "track", label: "热门赛道", source: "track_crowding" }
] as const;

type RankCategoryKey = (typeof RANK_CATEGORIES)[number]["key"];

const RANK_VIEWS = [
  {
    key: "crowding",
    label: "拥挤度",
    info: {
      sw: "申万一级 31 个行业的历史分位：综合拥挤度、成交额占全A比例、换手率、60 日线上占比、60 日新高占比、融资买入占比、百万大单。越高越拥挤。数据来自外部临时源；PB 分位需行业 PB 源，当前留空。",
      track:
        "18 个热门赛道（概念指数 + 申万细分，如 AI芯片 / 半导体设备 / 光通信）的历史分位，维度同行业视图；赛道维度无行业乖离率。数据来自外部临时源。"
    },
    staleTip:
      "数据源（外部临时源 / 申万宏源官网）暂不可用，当前为最近一次成功计算的结果或占位提示，非实时数据，仅供参考。"
  },
  {
    key: "bias",
    label: "乖离率",
    info: {
      sw: "LOGBIAS = (ln(收盘) − EMA20(ln(收盘))) × 100：正 = 位于均线上方（偏热），负 = 下方（偏冷）；档位阈值 ±15 / ±5。",
      track: "赛道维度不提供行业乖离率（该口径仅申万一级行业适用）。"
    },
    staleTip:
      "行情源（申万宏源官网 / 腾讯）暂不可用，当前乖离率基于最近一次成功抓取的价格计算，非实时数据，仅供参考。"
  }
] as const;

type RankViewKey = (typeof RANK_VIEWS)[number]["key"];

const rankCategory = ref<RankCategoryKey>("sw");
const rankView = ref<RankViewKey>("crowding");

/** 切换分类：赛道无乖离率 → 自动回到拥挤度视图，避免停在空视图 */
const switchCategory = (key: RankCategoryKey) => {
  rankCategory.value = key;
  if (key === "track") rankView.value = "crowding";
};

/** 当前分类下可用的视图（赛道仅拥挤度） */
const availableRankViews = computed(() =>
  rankCategory.value === "track"
    ? RANK_VIEWS.filter(v => v.key === "crowding")
    : RANK_VIEWS
);

/** 分位色标图例：阈值与 crowdingColorClass 同源，避免文案与实现不一致 */
const RANK_LEGEND = [
  {
    label: `低迷 <${CROWDING_LOW_THRESHOLD}`,
    dotClass: "rank-legend__dot--low"
  },
  {
    label: `中性 ${CROWDING_LOW_THRESHOLD}–${CROWDING_HIGH_THRESHOLD}`,
    dotClass: "rank-legend__dot--mid"
  },
  {
    label: `过热 >${CROWDING_HIGH_THRESHOLD}`,
    dotClass: "rank-legend__dot--high"
  }
];

/** 外部临时源提示（#1431 决策：先用它补维度，但如实告知来源与限制） */
const EXTERNAL_SOURCE_NOTICE = {
  tone: "info",
  icon: "ep:info-filled",
  text: "当前为外部临时源数据（fundfof.com 公开接口），含换手率 / 60日线上占比 / 新高占比 / 融资买入占比 / 百万大单等维度。该源未授权、可能随时失效，仅供自用参考；我方自有数据源就位后将替换。"
};

/** 降级提示：外部源不可用 → 已回落申万官网自算，维度变少（提示而非报错） */
const DEGRADED_SOURCE_NOTICE = {
  tone: "warning",
  icon: "ep:warning",
  text: "外部源当前不可用，已自动降级为申万宏源官网自算：仅提供成交额占比分位与乖离率；换手率 / 60日线上占比 / 新高占比 / 融资买入占比 / 百万大单 暂不可用。"
};

// ================================================================
// 计算属性
// ================================================================
const updatedAt = computed(() => overview.value?.updated_at || "");

/** 当前「分类 × 视图」对应的提示、更新时间与滞后状态（标题行统一展示） */
const activeRankView = computed(() => {
  const view = RANK_VIEWS.find(v => v.key === rankView.value) ?? RANK_VIEWS[0];
  const isCrowding = rankView.value === "crowding";
  const isTrack = rankCategory.value === "track";
  return {
    info: view.info[rankCategory.value],
    staleTip: view.staleTip,
    date: isCrowding
      ? isTrack
        ? trackDate.value
        : crowdingDate.value
      : biasDate.value,
    stale: isCrowding
      ? isTrack
        ? trackStale.value
        : crowdingStale.value
      : biasStale.value
  };
});

const compositeValue = computed(
  () => compositeTemperature.value?.value ?? null
);

// 等级文案与概览档同源同文案（含「暂无」兜底）：缺数据时不能兜成 TemperatureLevelBadge
// 的默认「适中」——那会在无数据时给出「市场平稳」的错误结论（#1549 T4.1）。
const compositeLevel = computed(
  () => compositeTemperature.value?.level || "暂无"
);

// 温度解读卡（TemperatureContextCard）所需数据，从 composable 的 fearData 推导
const fearGreedValue = computed<number | null>(() => {
  const v = fearData.value?.value;
  return typeof v === "number" ? v : null;
});
const fearGreedLabel = computed(() => fearData.value?.label || "");

const tempPeriods = computed(() => {
  const bands = overview.value?.composites?.temperature_bands;
  if (!bands) return [];
  return (["short", "medium", "long"] as const)
    .map(k => bands[k])
    .filter(Boolean)
    .map((b: { name?: string; value?: number }) => ({
      label: b.name || "",
      value: typeof b.value === "number" ? b.value : null
    }));
});

// 全部单值指标（过滤核心指标，按数据分层展示）
const detailMetrics = computed(() => {
  const singles = overview.value?.singles || [];
  return singles.filter((s: any) => !CORE_SINGLE_SOURCES.includes(s.source));
});

// 过滤整组标灰占位（item_code === '__NA__'），仅展示有效行业
const crowdingValidItems = computed(() =>
  (crowdingItems.value || []).filter((i: any) => i.item_code !== "__NA__")
);

// 赛道同理（外部源关停时该 source 可能整组无数据）
const trackValidItems = computed(() =>
  (trackItems.value || []).filter((i: any) => i.item_code !== "__NA__")
);

/** 当前分类下的拥挤度条目（行业 / 赛道共用同一张表） */
const activeCrowdingItems = computed(() =>
  rankCategory.value === "track"
    ? trackValidItems.value
    : crowdingValidItems.value
);

const activeCrowdingLoading = computed(() =>
  rankCategory.value === "track" ? trackLoading.value : crowdingLoading.value
);

/**
 * 数据来源提示（#1431）：按当前展示的数据判定，只提示、不报错。
 * 外部临时源 → 蓝色说明；已降级为申万自算（维度缺项）→ 黄色提醒；无数据时不提示（由表格空态负责）。
 */
const sourceNotice = computed(() => {
  const items = activeCrowdingItems.value;
  if (!items.length) return null;
  const isExternal = items.some(
    (i: any) => i.data?.source_kind === "external_temp"
  );
  return isExternal ? EXTERNAL_SOURCE_NOTICE : DEGRADED_SOURCE_NOTICE;
});

// ================================================================
// 方法
// ================================================================
const fetchBias = async () => {
  biasLoading.value = true;
  try {
    const res = await getMultiItems("bias");
    const data = res.data;
    if (data && data.items) {
      biasItems.value = data.items;
      biasDate.value = data.date || "";
      biasStale.value =
        Boolean(data.stale) || (data.items || []).some((i: any) => i.stale);
    } else {
      biasItems.value = [];
      biasStale.value = false;
    }
  } catch (e) {
    console.error("获取乖离率数据失败:", e);
    biasItems.value = [];
    biasDate.value = "";
    biasStale.value = false;
  } finally {
    biasLoading.value = false;
  }
};

const fetchCrowding = async () => {
  crowdingLoading.value = true;
  try {
    const res = await getMultiItems("industry_crowding");
    const data = res.data;
    if (data && data.items) {
      crowdingItems.value = data.items;
      crowdingDate.value = data.date || "";
      crowdingStale.value =
        Boolean(data.stale) || (data.items || []).some((i: any) => i.stale);
    } else {
      crowdingItems.value = [];
      crowdingStale.value = false;
    }
  } catch (e) {
    console.error("获取行业拥挤度数据失败:", e);
    crowdingItems.value = [];
    crowdingDate.value = "";
    crowdingStale.value = false;
  } finally {
    crowdingLoading.value = false;
  }
};

// 热门赛道（外部临时源 category=track）：失败静默为空，赛道视图显示空态提示，不影响行业视图
const fetchTrack = async () => {
  trackLoading.value = true;
  try {
    const res = await getMultiItems("track_crowding");
    const data = res.data;
    if (data && data.items) {
      trackItems.value = data.items;
      trackDate.value = data.date || "";
      trackStale.value =
        Boolean(data.stale) || (data.items || []).some((i: any) => i.stale);
    } else {
      trackItems.value = [];
      trackStale.value = false;
    }
  } catch (e) {
    console.error("获取赛道拥挤度数据失败:", e);
    trackItems.value = [];
    trackDate.value = "";
    trackStale.value = false;
  } finally {
    trackLoading.value = false;
  }
};

// 温度 store：承载综合温度、股债性价比与市场机会清单
const tempStore = useTemperatureStore();

// ================================================================
// 生命周期
// ================================================================
onMounted(async () => {
  await fetchTemperature();
  await fetchBias();
  await fetchCrowding();
  await fetchTrack();
  // NOTE: 与 useTemperatureOverview 各自调用一次 getTemperatureOverview，后续可合并为单一数据源
  await tempStore.fetchTemperature();
});
</script>

<style lang="scss" scoped>
/* 数据新鲜度守卫横幅（#1431）：沿用「数据滞后」pill 的警示色视觉语言 */
.freshness-alert {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-warning, #d97706);
  background: color-mix(
    in srgb,
    var(--color-warning, #d97706) 12%,
    transparent
  );
  border: 1px solid
    color-mix(in srgb, var(--color-warning, #d97706) 35%, transparent);
  border-radius: 8px;
}

.freshness-alert__icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.freshness-alert__text {
  flex: 1;
}

/* ===== 响应式 ===== */
@media (width <= 960px) {
  .context-grid {
    grid-template-columns: 1fr;
  }
}

@media (width <= 768px) {
  .detail-panel {
    padding: 16px;
  }
}

/* 深度档容器：与概览档共用同一套页面边距与最大宽度 */
.detail-panel {
  max-width: 1280px;
  padding: var(--space-standard) 24px 16px;
  margin: 0 auto;
}

/* 仪表盘区域 */
.dashboard-section {
  margin-bottom: 24px;
}

.context-section {
  margin-bottom: 24px;
}

/* ============================================================
   温度解读 + 市场机会（并排）
   ============================================================ */
.context-grid {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 16px;
  align-items: stretch;
}

.context-card,
.opportunity-card {
  overflow: hidden;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.opportunity-card {
  display: flex;
  flex-direction: column;
  padding: 16px;
}

.opportunity-card :deep(.section-header) {
  margin-bottom: 12px;
}

.opportunity-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
}

.opportunity-item {
  padding: 12px 14px;
  background: var(--bg-subtle);
  border-left: 4px solid var(--border-light);
  border-radius: 10px;
}

.opportunity-item--safe {
  background: color-mix(in srgb, var(--temp-low) 8%, var(--bg-subtle));
  border-left-color: var(--temp-low);
}

.opportunity-item--danger {
  background: color-mix(in srgb, var(--temp-high) 8%, var(--bg-subtle));
  border-left-color: var(--temp-high);
}

.opportunity-item--neutral {
  background: color-mix(in srgb, var(--temp-mid) 8%, var(--bg-subtle));
  border-left-color: var(--temp-mid);
}

.opportunity-head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.opportunity-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.opportunity-tag {
  padding: 2px 8px;
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  background: var(--border-light);
  border-radius: 10px;
}

.opportunity-item--safe .opportunity-tag {
  color: var(--temp-low);
  background: color-mix(in srgb, var(--temp-low) 18%, transparent);
}

.opportunity-item--danger .opportunity-tag {
  color: var(--temp-high);
  background: color-mix(in srgb, var(--temp-high) 18%, transparent);
}

.opportunity-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
}

/* ============================================================
   行业排行（#1431）：拥挤度 / 乖离率双视图共用一张卡片
   卡片外观统一由 CardBlock 提供（docs/design/components.md「CardBlock · 区块卡片容器」），
   本页只保留区块外边距，禁在此重复手写 token 卡片样式
   ============================================================ */
.industry-rank-section {
  margin-bottom: 24px;
}

.rank-updated {
  font-size: 12px;
  color: var(--text-tertiary);
}

.rank-stale-pill {
  padding: 2px 8px;
  margin-left: 8px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--color-warning, #d97706);
  white-space: nowrap;
  cursor: help;
  background: color-mix(
    in srgb,
    var(--color-warning, #d97706) 12%,
    transparent
  );
  border: 1px solid
    color-mix(in srgb, var(--color-warning, #d97706) 35%, transparent);
  border-radius: 6px 6px 6px 0;
}

/* 果冻胶囊按钮组（docs/design/components.md「果冻胶囊按钮组（D13）」） */
.rank-switch {
  display: inline-flex;
  gap: 6px;
  margin-right: 12px;
}

.rank-switch__item {
  padding: 4px 14px;
  font-size: 13px;
  color: var(--text-tertiary);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transform: translateZ(0);
  transform-origin: center;
  transition:
    color 0.18s ease,
    background-color 0.18s ease,
    border-color 0.18s ease,
    transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1);
  will-change: transform;
}

.rank-switch__item:hover {
  color: var(--text-primary);
  border-color: var(--brand-400);
}

.rank-switch__item:active {
  transform: translateZ(0) scale(0.92);
}

/* 果冻回弹关键帧（docs/design/components.md「果冻胶囊按钮组（D13）」） */
@keyframes style-pop {
  0% {
    transform: translateZ(0) scale(1);
  }

  30% {
    transform: translateZ(0) scale(0.92);
  }

  60% {
    transform: translateZ(0) scale(1.05);
  }

  80% {
    transform: translateZ(0) scale(0.97);
  }

  100% {
    transform: translateZ(0) scale(1);
  }
}

.rank-switch__item:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.rank-switch__item--active {
  color: var(--brand-700);
  background: var(--brand-100);
  border-color: var(--brand-400);
  box-shadow: 0 1px 3px rgb(0 0 0 / 6%);
  animation: style-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* ============================================================
   数据来源提示条 + 分位色标图例（#1431）
   ============================================================ */
.rank-source-notice {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 12px;
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
  border-radius: 8px;
}

.rank-source-notice--info {
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--brand-400) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--brand-400) 30%, transparent);
}

.rank-source-notice--warning {
  color: var(--color-warning, #d97706);
  background: color-mix(
    in srgb,
    var(--color-warning, #d97706) 10%,
    transparent
  );
  border: 1px solid
    color-mix(in srgb, var(--color-warning, #d97706) 32%, transparent);
}

.rank-source-notice__icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.rank-source-notice__text {
  flex: 1;
}

.rank-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.rank-legend__item {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.rank-legend__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.rank-legend__dot--low {
  background: var(--temp-low);
}

.rank-legend__dot--mid {
  background: var(--temp-mid);
}

.rank-legend__dot--high {
  background: var(--temp-high);
}

/* 表格视觉基线由全站统一主题维护（src/style/el-table.css），勿在本页 :deep 覆盖 */
</style>
