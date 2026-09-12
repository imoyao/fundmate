<script setup lang="ts">
// 探市·大类资产观察区块（#1436 / #1444 收口实现）。
// 落在既有探市页（views/explore/）内，紧接温度仪表盘之后。
// 数据驱动渲染 6 组 × 资产卡片，复用 RiseFallText（涨红跌绿）、SectionHeader，
// 相对位置条复用温度三色 token（--temp-low/mid/high）。不可得资产软占位（置灰 + — + 原因）。
import { computed, onMounted } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { useMarketOverview } from "@/composables/market/useMarketOverview";
import type { MarketAsset, MarketGroup } from "@/api/market";

const { loading, error, overview, fetchOverview } = useMarketOverview();

const groups = computed<MarketGroup[]>(() => overview.value?.groups ?? []);
const asOfNote = computed(() => overview.value?.as_of_note ?? "");
const unavailableCount = computed(() => overview.value?.unavailable_count ?? 0);
const bondYield = computed(() => overview.value?.bond_yield ?? null);
const updatedAt = computed(() => overview.value?.updated_at ?? "");

// 分类 → 资产类别色 token（复用项目既有 --asset-* 族，无商品专属 token，商品映射到 etf 薄荷绿）
const CATEGORY_TOKEN: Record<string, string> = {
  A股: "var(--asset-stock)",
  港股: "var(--asset-stock)",
  海外: "var(--asset-stock)",
  债券: "var(--asset-bond)",
  商品: "var(--asset-etf)",
  汇率: "var(--asset-saving)"
};

const categoryColor = (category: string) =>
  CATEGORY_TOKEN[category] || "var(--text-secondary)";

// 相对位置分位 → 温度三色（偏低绿 / 适中沙 / 偏高红）
const positionColor = (asset: MarketAsset): string => {
  const label = asset.position?.label;
  if (label === "偏低") return "var(--temp-low)";
  if (label === "偏高") return "var(--temp-high)";
  return "var(--temp-mid)";
};

// 收益率变动(bp) 用中性色，不套用涨红跌绿（§3.4 纪律）
const yieldTone = (_bp?: number) => "var(--text-secondary)";

onMounted(() => {
  fetchOverview();
});
</script>

<template>
  <section class="asset-overview">
    <!-- 区块标题 -->
    <SectionHeader title="大类资产观察" />

    <!-- 市场状态条：各市场数据截止口径 -->
    <div v-if="asOfNote" class="asof-bar">
      <IconifyIconOffline icon="ep:info-filled" class="asof-bar__icon" />
      <span class="asof-bar__text">{{ asOfNote }}</span>
    </div>

    <!-- 加载 / 错误态 -->
    <div v-if="loading" class="state-hint">数据加载中…</div>
    <div v-else-if="error" class="state-hint state-hint--error">
      资产观察数据加载失败：{{ error }}
    </div>

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
              <span class="asset-card__name">{{ asset.name }}</span>
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
                  <span class="pos-bar__basis">{{ asset.position.basis }}</span>
                  <span
                    class="pos-bar__label"
                    :style="{ color: positionColor(asset) }"
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
  </section>
</template>

<style lang="scss" scoped>
.asset-overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1280px;
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
    color: var(--text-tertiary);
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
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
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

    &--na {
      font-family: var(--font-mono);
      font-size: 28px;
      font-weight: 700;
      color: var(--text-disabled);
    }
  }

  &__reason {
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-disabled);
  }

  &__nopin {
    font-family: var(--font-mono);
    font-size: 18px;
    color: var(--text-disabled);
  }

  &__caliber-text {
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-tertiary);
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
    color: var(--text-tertiary);
  }

  &__label {
    font-size: 13px;
    font-weight: 600;
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
    color: var(--text-tertiary);
  }
}

/* 页脚统计 */
.overview-footer {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: flex-end;
  font-size: 13px;
  color: var(--text-tertiary);

  &__time {
    color: var(--text-tertiary);
  }
}

/* 响应式 */
@media (width <= 768px) {
  .asset-overview {
    padding: 0 16px 12px;
  }

  .asset-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  }

  .bond-yield__hint {
    margin-left: 0;
  }
}
</style>
