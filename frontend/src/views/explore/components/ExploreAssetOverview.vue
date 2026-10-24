<script setup lang="ts">
// 探市·大类资产观察区块（#1436 / #1444 收口实现）。
// 落在既有探市页（views/explore/）内，紧接温度仪表盘之后。
// 数据驱动渲染 6 组 × 资产卡片，复用 RiseFallText（涨红跌绿）、SectionHeader，
// 相对位置条复用温度三色 token（--temp-low/mid/high）。不可得资产软占位（置灰 + — + 原因）。
//
// 本文件只留「外壳」：标题行的展开/收起、折叠态摘要、取数三态（骨架 / 慢加载 / 错误）与页脚。
// 分组与卡片、异动面板、债券轨各自成组件（assetOverview/），展示口径是可单测的纯函数。
import { computed, onMounted, ref, watch } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import { useMarketOverview } from "@/composables/market/useMarketOverview";
import type { MarketGroup } from "@/api/market";
import { ASSET_CATEGORIES } from "@/constants/market";
import AssetAnomalyPanel from "./assetOverview/AssetAnomalyPanel.vue";
import AssetBondYield from "./assetOverview/AssetBondYield.vue";
import AssetGroupHeading from "./assetOverview/AssetGroupHeading.vue";
import AssetGroupSection from "./assetOverview/AssetGroupSection.vue";
import {
  collapsedCountText,
  flattenAnomalies,
  loadedAssetCountOf
} from "./assetOverview/assetOverviewModel";

const { loading, error, overview, fetchOverview, showSkeleton, slow } =
  useMarketOverview();

const groups = computed<MarketGroup[]>(() => overview.value?.groups ?? []);

/** ⚡ 命中异动的资产（扁平化后供区块底部「异动解读」渲染） */
const anomalyAssets = computed(() => flattenAnomalies(groups.value));
const asOfNote = computed(() => overview.value?.as_of_note ?? "");
const unavailableCount = computed(() => overview.value?.unavailable_count ?? 0);
const bondYield = computed(() => overview.value?.bond_yield ?? null);
const updatedAt = computed(() => overview.value?.updated_at ?? "");

// ================================================================
// #1546 T2.2：折叠容器——默认折叠为 6 条分组摘要，展开才请求 / 渲染 20 张卡
//
// 目的：把冷启动耗时长的 /api/market/overview 从首屏关键路径上摘掉。
// 折叠态一个请求都不发（治本仍在 #1460 落库）。
//
// #1671 方案 b：本区块已由概览档移入**深度档**，概览档只留一个入口。用户点入口跳来时
// 父级会传 defaultExpanded=true，此处直接以展开态渲染并取数——避免「按入口跳过来
// 还得再点一次展开」；自然逛进深度档的用户仍是折叠态，不白白触发这个慢接口。
// ================================================================
const props = withDefaults(
  defineProps<{
    /** 是否默认展开（概览档入口跳转时传 true） */
    defaultExpanded?: boolean;
  }>(),
  { defaultExpanded: false }
);

const expanded = ref(props.defaultExpanded);

/** 折叠态的分组摘要来源：前端已知的 6 大分类（静态常量，无需请求接口） */
const collapsedCategories = ASSET_CATEGORIES;

/** 已加载的标的总数；尚未加载时回退到区块标称的 20 个，仅用于按钮文案 */
const loadedAssetCount = computed(() => loadedAssetCountOf(groups.value));

/** 仅在「还没数据且没在取」时取数：展开过之后直接复用已加载的数据，不会每次展开都重打接口 */
const ensureLoaded = () => {
  if (overview.value === null && !loading.value) {
    void fetchOverview();
  }
};

const toggleExpand = () => {
  expanded.value = !expanded.value;
  if (expanded.value) ensureLoaded();
};

// 概览档入口跳来时（本组件可能早已挂载）切到展开态
watch(
  () => props.defaultExpanded,
  v => {
    if (v && !expanded.value) {
      expanded.value = true;
      ensureLoaded();
    }
  }
);

// 挂载即为展开态时补一次取数（此时既不会走 toggleExpand，也不会触发上面的 watch）
onMounted(() => {
  if (expanded.value) ensureLoaded();
});
</script>

<template>
  <section class="asset-overview">
    <!-- 区块标题 + 展开/收起（复用 SectionHeader 的 #action 槽，不另造标题行） -->
    <SectionHeader title="大类资产观察">
      <template #action>
        <button
          type="button"
          class="asset-overview__toggle"
          :aria-expanded="expanded ? 'true' : 'false'"
          aria-controls="asset-overview-body"
          @click="toggleExpand"
        >
          {{ expanded ? "收起" : "展开" }}
          <IconifyIconOffline
            :icon="expanded ? 'ep:arrow-up' : 'ep:arrow-down'"
          />
        </button>
      </template>
    </SectionHeader>

    <!-- 折叠态：6 条分组摘要（静态分类，不请求接口 → 首屏不再依赖 /api/market/overview） -->
    <div v-if="!expanded" class="collapse-summary">
      <ul class="collapse-summary__list">
        <li
          v-for="cat in collapsedCategories"
          :key="cat"
          class="collapse-summary__item"
        >
          <AssetGroupHeading
            :category="cat"
            :count-text="collapsedCountText(groups, cat)"
          />
        </li>
      </ul>
      <button
        type="button"
        class="collapse-summary__btn"
        :aria-expanded="expanded ? 'true' : 'false'"
        aria-controls="asset-overview-body"
        @click="toggleExpand"
      >
        展开查看 {{ loadedAssetCount }} 个标的
        <IconifyIconOffline icon="ep:arrow-down" />
      </button>
    </div>

    <!-- 展开态：首次展开才取数，随后渲染 20 张卡 -->
    <div v-else id="asset-overview-body">
      <!-- 市场状态条：各市场数据截止口径 -->
      <div v-if="asOfNote" class="asof-bar">
        <IconifyIconOffline icon="ep:info-filled" class="asof-bar__icon" />
        <span class="asof-bar__text">{{ asOfNote }}</span>
      </div>

      <!-- 错误态优先（含重试，见 #1546 T2.5） -->
      <div v-if="error" class="state-hint state-hint--error">
        资产观察数据加载失败：{{ error }}
        <button
          type="button"
          class="state-hint__retry"
          @click="() => fetchOverview()"
        >
          重试
        </button>
      </div>
      <!-- 加载态：200ms 后才显示骨架屏，快速返回跳过骨架（#1546 T2.3，阈值逻辑在 composable） -->
      <PageSkeleton
        v-else-if="loading && showSkeleton && !slow"
        :cards="6"
        :table-rows="6"
      />
      <!-- 慢加载降级：>8s 仍未返回，提示可先浏览下方 + 重试（#1546 T2.5，请求不中断） -->
      <div v-else-if="loading && slow" class="state-hint state-hint--slow">
        数据加载较慢，可先浏览下方观察列表
        <button
          type="button"
          class="state-hint__retry"
          @click="() => fetchOverview()"
        >
          重试
        </button>
      </div>

      <!-- 6 组资产 -->
      <AssetGroupSection
        v-for="group in groups"
        :key="group.category"
        :group="group"
      />

      <!-- ⚡ 异动解读（§6.1 区块底部）：列出当日命中双线规则的资产 + 规则自述 -->
      <AssetAnomalyPanel v-if="anomalyAssets.length" :items="anomalyAssets" />

      <!-- 债券收益率轨（双轨：价格轨在卡片，收益率轨在此单独展示，不套涨红跌绿） -->
      <AssetBondYield v-if="bondYield" :bond-yield="bondYield" />

      <!-- 页脚统计：软占位数量 + 更新时刻 -->
      <div v-if="overview" class="overview-footer">
        <span>软占位 {{ unavailableCount }} 项（缺源 / 决策占位）</span>
        <span v-if="updatedAt" class="overview-footer__time"
          >更新于 {{ updatedAt }}</span
        >
      </div>
    </div>
  </section>
</template>

<style lang="scss" scoped>
.asset-overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: var(--layout-content-width);
  padding: var(--space-standard) 24px 16px;
  margin: 0 auto;
}

/* 市场状态条 */
.asof-bar {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 14px;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);

  &__icon {
    flex-shrink: 0;
    margin-top: 2px;
    font-size: var(--text-body);

    /* audit-text-contrast: exempt 非文本图形（图标字形），按 WCAG 1.4.11 需 3:1，本令牌在页底 / 卡片底实测 3.57~3.69:1，达标；
       若改用 -ink 会与相邻正文同权，反而压平层级。登记见 docs/spec/tech-debt.md（#1586） */
    color: var(--text-tertiary);
  }

  &__text {
    font-size: var(--text-label);
    line-height: 1.6;
    color: var(--text-secondary);
  }
}

.state-hint {
  padding: 24px;
  font-size: var(--text-small);
  color: var(--text-secondary);
  text-align: center;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);

  &--error {
    color: var(--color-danger);
  }

  &--slow {
    color: var(--text-secondary);
    background: var(--bg-soft);
  }

  &__retry {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    padding: 4px 12px;
    margin-left: 10px;
    font-family: inherit;
    font-size: var(--text-label);
    color: var(--brand-700);
    cursor: pointer;
    background: var(--brand-100);
    border: 1px solid var(--brand-400);
    border-radius: var(--radius-pill);
    transition: background-color 150ms ease;

    &:hover {
      background: var(--brand-200);
    }

    &:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
    }
  }
}

/* ============================================================
   #1546 T2.2：折叠容器
   - 折叠态只渲染 6 条分组摘要（静态分类，不请求接口）
   - 展开/收起按钮复用 SectionHeader 的 #action 槽，不另造标题行
   ============================================================ */
.collapse-summary {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);

  &__list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 10px;
    padding: 0;
    margin: 0;
    list-style: none;
  }

  &__item {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  &__btn {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    align-self: flex-start;
    padding: 6px 14px;
    font-family: inherit;
    font-size: var(--text-label);
    font-weight: 500;
    color: var(--brand-700);
    cursor: pointer;
    background: var(--brand-100);
    border: 1px solid var(--brand-400);
    border-radius: var(--radius-pill);
    transition: background-color 150ms ease;

    &:hover {
      background: var(--brand-200);
    }

    &:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
    }
  }
}

.asset-overview__toggle {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 4px 12px;
  font-family: inherit;
  font-size: var(--text-label);
  color: var(--text-secondary);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;

  &:hover {
    color: var(--text-primary);
    background: var(--bg-hover);
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }
}

/* 页脚统计 */
.overview-footer {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: flex-end;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);

  &__time {
    color: var(--text-tertiary-ink);
  }
}

/* 响应式（#1549 T4.3）：栅格列数在 AssetGroupSection 内各自生效，此处只调根内边距 */
@media (width <= 768px) {
  .asset-overview {
    padding: 0 16px 12px;
  }
}
</style>
