<script setup lang="ts">
// 探市·大类资产观察区块（#1436 / #1444 收口实现）。
// 落在既有探市页（views/explore/）内，紧接温度仪表盘之后。
// 数据驱动渲染 6 组 × 资产卡片，复用 RiseFallText（涨红跌绿）、SectionHeader，
// 相对位置条复用温度三色 token（--temp-low/mid/high）。不可得资产软占位（置灰 + — + 原因）。
import { computed, ref } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import { useMarketOverview } from "@/composables/market/useMarketOverview";
import type { MarketAnomaly, MarketAsset, MarketGroup } from "@/api/market";

const { loading, error, overview, fetchOverview, showSkeleton } =
  useMarketOverview();

const groups = computed<MarketGroup[]>(() => overview.value?.groups ?? []);

/** ⚡ 命中异动的资产（扁平化后供区块底部「异动解读」渲染） */
const anomalyAssets = computed<
  { asset: MarketAsset; anomaly: MarketAnomaly }[]
>(() =>
  groups.value
    .flatMap(group => group.assets)
    .map(asset => ({ asset, anomaly: asset.anomaly }))
    .filter(
      (x): x is { asset: MarketAsset; anomaly: MarketAnomaly } =>
        x.anomaly !== null
    )
);
const asOfNote = computed(() => overview.value?.as_of_note ?? "");
const unavailableCount = computed(() => overview.value?.unavailable_count ?? 0);
const bondYield = computed(() => overview.value?.bond_yield ?? null);
const updatedAt = computed(() => overview.value?.updated_at ?? "");

// 分类 → 品种色 token（唯一真相源 --asset-cat-*；无商品专属 token，商品映射到 etf 绿）
const CATEGORY_TOKEN: Record<string, string> = {
  A股: "var(--asset-cat-stock)",
  港股: "var(--asset-cat-stock)",
  海外: "var(--asset-cat-stock)",
  债券: "var(--asset-cat-bond)",
  商品: "var(--asset-cat-etf)",
  汇率: "var(--asset-cat-saving)"
};

const categoryColor = (category: string) =>
  CATEGORY_TOKEN[category] || "var(--text-secondary)";

// 相对位置分位 → 温度三色（偏低绿 / 适中沙 / 偏高红）
// #1545 拆两族：游标等「图形 / 实色」用 --temp-*；
// 标签文字必须用 --temp-*-ink（实色作文字对比度不足，白底仅 1.68–3.96:1）。
const positionColor = (asset: MarketAsset): string => {
  const label = asset.position?.label;
  if (label === "偏低") return "var(--temp-low)";
  if (label === "偏高") return "var(--temp-high)";
  return "var(--temp-mid)";
};

const positionLabelColor = (asset: MarketAsset): string => {
  const label = asset.position?.label;
  if (label === "偏低") return "var(--temp-low-ink)";
  if (label === "偏高") return "var(--temp-high-ink)";
  return "var(--temp-mid-ink)";
};

// 收益率变动(bp) 用中性色，不套用涨红跌绿（§3.4 纪律）
const yieldTone = (_bp?: number) => "var(--text-secondary)";

// ================================================================
// #1546 T2.2：折叠容器——默认折叠为 6 条分组摘要，展开才请求 / 渲染 20 张卡
//
// 目的：把冷启动耗时长的 /api/market/overview 从首屏关键路径上摘掉。
// 折叠态一个请求都不发，首屏可交互时间不再依赖该接口（治本仍在 #1460 落库）。
// ================================================================
const expanded = ref(false);

/** 折叠态的分组摘要来源：前端已知的 6 大分类（与 CATEGORY_TOKEN 同源，无需请求接口） */
const collapsedCategories = Object.keys(CATEGORY_TOKEN);

/** 已加载数据时的分组标的数；未加载返回 null（折叠态就不显示数字，避免编造） */
const groupCount = (category: string): number | null => {
  const group = groups.value.find(g => g.category === category);
  return group ? group.assets.length : null;
};

/** 已加载的标的总数；尚未加载时回退到区块标称的 20 个，仅用于按钮文案 */
const loadedAssetCount = computed(() => {
  const total = groups.value.reduce((n, g) => n + g.assets.length, 0);
  return total > 0 ? total : 20;
});

const toggleExpand = () => {
  expanded.value = !expanded.value;
  // 仅首次展开才取数：展开过之后直接复用已加载的数据，不会每次展开都重打接口
  if (expanded.value && overview.value === null && !loading.value) {
    void fetchOverview();
  }
};
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
          <span
            class="asset-group__dot"
            :style="{ background: categoryColor(cat) }"
          />
          <span class="asset-group__title">{{ cat }}</span>
          <span v-if="groupCount(cat) !== null" class="asset-group__count">
            {{ groupCount(cat) }} 个标的
          </span>
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

      <!-- 错误态优先 -->
      <div v-if="error" class="state-hint state-hint--error">
        资产观察数据加载失败：{{ error }}
      </div>
      <!-- 加载态：200ms 后才显示骨架屏，快速返回跳过骨架（#1546 T2.3，阈值逻辑在 composable） -->
      <PageSkeleton
        v-else-if="loading && showSkeleton"
        :cards="6"
        :table-rows="6"
      />

      <!-- 6 组资产 -->
      <template v-for="group in groups" :key="group.category">
        <div class="asset-group">
          <div class="asset-group__head">
            <span
              class="asset-group__dot"
              :style="{ background: categoryColor(group.category) }"
            />
            <span class="asset-group__title">{{ group.category }}</span>
            <span class="asset-group__count">{{ group.assets.length }}</span>
          </div>

          <div class="asset-grid">
            <!-- 单资产卡片（数据驱动，不写 20 份模板） -->
            <div
              v-for="asset in group.assets"
              :key="asset.key"
              class="asset-card"
              :class="{ 'asset-card--disabled': !asset.available }"
            >
              <div class="asset-card__top">
                <span class="asset-card__name">
                  {{ asset.name }}
                  <!-- ⚡ 异动标记（§5.5 双线规则），命中才渲染；用图标而非 emoji（AGENTS.md 禁 emoji） -->
                  <span
                    v-if="asset.anomaly"
                    class="asset-card__anomaly"
                    :title="`异动：${asset.anomaly.basis_note}`"
                  >
                    <IconifyIconOffline icon="ep:lightning" />
                  </span>
                </span>
                <span
                  v-if="asset.caliber"
                  class="asset-card__caliber"
                  :title="asset.caliber"
                  >口径</span
                >
              </div>

              <!-- 软占位：置灰 + — + 原因 -->
              <template v-if="!asset.available">
                <div class="asset-card__change asset-card__change--na">—</div>
                <div class="asset-card__reason">{{ asset.reason }}</div>
              </template>

              <!-- 可取数 -->
              <template v-else>
                <div class="asset-card__change">
                  <RiseFallText
                    :value="asset.change_pct ?? 0"
                    :precision="2"
                    size="lg"
                  />
                </div>

                <!-- 相对位置条（温度三色 + 游标） -->
                <div
                  v-if="asset.position"
                  class="pos-bar"
                  :title="`${asset.position.basis} · 近${asset.position.window}日分位 ${asset.position.percentile}%`"
                >
                  <div class="pos-bar__track">
                    <div
                      class="pos-bar__cursor"
                      :style="{
                        left: asset.position.percentile + '%',
                        background: positionColor(asset)
                      }"
                    />
                  </div>
                  <div class="pos-bar__meta">
                    <span class="pos-bar__basis">{{
                      asset.position.basis
                    }}</span>
                    <span
                      class="pos-bar__label"
                      :style="{ color: positionLabelColor(asset) }"
                      >{{ asset.position.label }}</span
                    >
                  </div>
                </div>
                <div v-else class="asset-card__nopin">—</div>

                <div v-if="asset.caliber" class="asset-card__caliber-text">
                  {{ asset.caliber }}
                </div>
              </template>
            </div>
          </div>
        </div>
      </template>

      <!-- ⚡ 异动解读（§6.1 区块底部）：列出当日命中双线规则的资产 + 规则自述 -->
      <div v-if="anomalyAssets.length" class="anomaly-panel">
        <div class="anomaly-panel__head">
          <IconifyIconOffline icon="ep:lightning" class="anomaly-panel__icon" />
          <span>异动解读</span>
          <span class="anomaly-panel__count"
            >{{ anomalyAssets.length }} 项</span
          >
        </div>
        <ul class="anomaly-panel__list">
          <li
            v-for="item in anomalyAssets"
            :key="item.asset.key"
            class="anomaly-item"
          >
            <span class="anomaly-item__name">{{ item.asset.name }}</span>
            <span class="anomaly-item__change">
              <RiseFallText
                :value="item.anomaly.today_pct"
                :precision="2"
                size="sm"
              />
            </span>
            <span class="anomaly-item__note">{{
              item.anomaly.basis_note
            }}</span>
          </li>
        </ul>
        <div class="anomaly-panel__foot">
          判定用「双线规则」：单日涨跌超过自身近
          {{ anomalyAssets[0].anomaly.sigma_window }} 个交易日波动（σ）的
          {{ anomalyAssets[0].anomaly.sigma_multiple }} 倍，或超过
          {{ anomalyAssets[0].anomaly.abs_threshold }}%
          绝对阈值。此处为规则自述，暂未接入新闻源。
        </div>
      </div>

      <!-- 债券收益率轨（双轨：价格轨在卡片，收益率轨在此单独展示，不套涨红跌绿） -->
      <div v-if="bondYield" class="bond-yield">
        <div class="bond-yield__head">债券收益率轨（双轨对照）</div>
        <div class="bond-yield__items">
          <div class="bond-yield__item">
            <span class="bond-yield__label">中债 10Y</span>
            <span class="bond-yield__val">{{ bondYield.cn_10y }}%</span>
            <span
              class="bond-yield__bp"
              :style="{ color: yieldTone(bondYield.cn_10y_change_bp) }"
              >{{ (bondYield.cn_10y_change_bp ?? 0) >= 0 ? "+" : ""
              }}{{ bondYield.cn_10y_change_bp ?? 0 }} bp</span
            >
          </div>
          <div v-if="bondYield.us_10y != null" class="bond-yield__item">
            <span class="bond-yield__label">美债 10Y</span>
            <span class="bond-yield__val">{{ bondYield.us_10y }}%</span>
            <span
              class="bond-yield__bp"
              :style="{ color: yieldTone(bondYield.us_10y_change_bp) }"
              >{{ (bondYield.us_10y_change_bp ?? 0) >= 0 ? "+" : ""
              }}{{ bondYield.us_10y_change_bp ?? 0 }} bp</span
            >
          </div>
          <span class="bond-yield__hint"
            >收益率上行 ≠ 利好，与价格轨涨跌语义相反</span
          >
        </div>
      </div>

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
    font-size: 15px;

    /* audit-text-contrast: exempt 非文本图形（图标字形），按 WCAG 1.4.11 需 3:1，本令牌在页底 / 卡片底实测 3.57~3.69:1，达标；
       若改用 -ink 会与相邻正文同权，反而压平层级。登记见 docs/spec/tech-debt.md（#1586） */
    color: var(--text-tertiary);
  }

  &__text {
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-secondary);
  }
}

.state-hint {
  padding: 24px;
  font-size: 14px;
  color: var(--text-secondary);
  text-align: center;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);

  &--error {
    color: var(--color-danger);
  }
}

/* 分组 */
.asset-group {
  display: flex;
  flex-direction: column;
  gap: 12px;

  &__head {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  &__dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }

  &__title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__count {
    font-size: 13px;
    color: var(--text-tertiary-ink);
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
    font-size: 13px;
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
  font-size: 13px;
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

/* 卡片网格：自适应 */
.asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.asset-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0; /* 允许在窄轨道内收窄，防「内容 min-content 顶宽 → 横向溢出」（#1549 T4.3） */
  padding: 14px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-raised);

  &--disabled {
    background: var(--bg-soft);
    border-style: dashed;
    box-shadow: none;
  }

  &__top {
    display: flex;
    gap: 6px;
    align-items: center;
    justify-content: space-between;
  }

  &__name {
    min-width: 0; /* 长名称换行而非顶宽（禁截断，故不加 ellipsis） */
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  /* ⚡ 异动标记：暖沙金底 + 品牌橙图标，刻意避开涨跌红绿语义 */
  &__anomaly {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0 3px;
    margin-left: 4px;
    font-size: 13px;
    line-height: 1.5;
    vertical-align: middle;
    color: var(--brand-700);
    cursor: help;
    background: var(--color-warning-20);
    border-radius: 4px;
  }

  &__caliber {
    flex-shrink: 0;
    padding: 1px 6px;
    font-size: 12px;
    color: var(--text-secondary);
    cursor: help;
    background: var(--bg-soft);
    border-radius: 4px;
  }

  &__change {
    font-variant-numeric: tabular-nums;

    /* 无数据占位「—」：原文案用 --text-disabled（1.67:1）在卡底近乎不可见，
       用户无法区分「无数据」与「渲染坏了」。占位符是信息，不是禁用控件，
       不适用 WCAG 对 inactive component 的豁免，故改用文字级令牌（5.78:1）。 */
    &--na {
      font-family: var(--font-mono);
      font-size: 28px;
      font-weight: 700;
      color: var(--text-tertiary-ink);
    }
  }

  /* 不可用原因说明：真实可读文案，13px 正文级 → 必须 ≥ 4.5:1 */
  &__reason {
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-tertiary-ink);
  }

  /* 同 &--na：占位「—」 */
  &__nopin {
    font-family: var(--font-mono);
    font-size: 18px;
    color: var(--text-tertiary-ink);
  }

  &__caliber-text {
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-tertiary-ink);
  }
}

/* 相对位置条 */
.pos-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;

  &__track {
    position: relative;
    height: 6px;
    background: linear-gradient(
      90deg,
      var(--temp-low) 0%,
      var(--temp-mid) 50%,
      var(--temp-high) 100%
    );
    border-radius: 3px;
  }

  &__cursor {
    position: absolute;
    top: 50%;
    width: 10px;
    height: 10px;
    border: 2px solid var(--text-inverse);
    border-radius: 50%;
    box-shadow: 0 0 0 1px rgb(0 0 0 / 10%);
    transform: translate(-50%, -50%);
  }

  &__meta {
    display: flex;
    gap: 6px;
    align-items: baseline;
    justify-content: space-between;
  }

  &__basis {
    font-size: 13px;
    color: var(--text-tertiary-ink);
  }

  &__label {
    font-size: 13px;
    font-weight: 600;
  }
}

/* ⚡ 异动解读面板 */
.anomaly-panel {
  padding: 14px 16px;
  background: var(--color-warning-20);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-md);

  &__head {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 10px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__icon {
    font-size: 16px;
    color: var(--brand-700);
  }

  &__count {
    font-size: 13px;
    font-weight: 400;
    color: var(--text-secondary);
  }

  &__list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 0;
    margin: 0;
    list-style: none;
  }

  &__foot {
    padding-top: 10px;
    margin-top: 10px;
    font-size: 12px;
    line-height: 1.6;
    color: var(--text-secondary);
    border-top: 1px solid var(--color-warning);
  }
}

.anomaly-item {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
  font-size: 13px;

  &__name {
    min-width: 72px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__change {
    font-variant-numeric: tabular-nums;
  }

  &__note {
    flex: 1 1 240px;
    line-height: 1.6;
    color: var(--text-secondary);
  }
}

/* 债券收益率轨 */
.bond-yield {
  padding: 14px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-raised);

  &__head {
    margin-bottom: 10px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__items {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    align-items: center;
  }

  &__item {
    display: flex;
    gap: 8px;
    align-items: baseline;
  }

  &__label {
    font-size: 13px;
    color: var(--text-secondary);
  }

  &__val {
    font-family: var(--font-mono);
    font-size: 18px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
  }

  &__bp {
    font-family: var(--font-mono);
    font-size: 13px;
    font-variant-numeric: tabular-nums;
  }

  &__hint {
    margin-left: auto;
    font-size: 13px;
    color: var(--text-tertiary-ink);
  }
}

/* 页脚统计 */
.overview-footer {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: flex-end;
  font-size: 13px;
  color: var(--text-tertiary-ink);

  &__time {
    color: var(--text-tertiary-ink);
  }
}

/* 响应式（#1549 T4.3）
   原实现 ≤768px 把栅格底线压到 140px：375px 视口下 auto-fill 会塞 2 列、每列仅
   ~165px，「指数名 + 口径标 + 相对位置条」挤在一起。改为显式列数，并把轨道写成
   minmax(0, 1fr) —— 允许轨道收窄到内容 min-content 以下，杜绝资产卡顶宽容器后横向溢出。 */
@media (width <= 768px) {
  .asset-overview {
    padding: 0 16px 12px;
  }

  /* 481–768px：两列（每列 218–368px），横向留白充足 */
  .asset-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .bond-yield__hint {
    margin-left: 0;
  }
}

@media (width <= 480px) {
  /* 375px 档：可用宽度 343px，两列仅 ~165px 过挤 → 单列满宽 */
  .asset-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
