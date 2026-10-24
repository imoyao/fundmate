<template>
  <div class="selected-asset-card__head">
    <span class="selected-asset-card__name" :title="rowColumns(asset).name">{{
      rowColumns(asset).name
    }}</span>
    <span
      v-if="rowColumns(asset).sub"
      class="selected-asset-card__sub"
      :title="rowColumns(asset).sub"
      >{{ rowColumns(asset).sub }}</span
    >
    <span
      class="selected-asset-card__type"
      :class="`selected-asset-card__type--${rowColumns(asset).typeKey}`"
      >{{ rowColumns(asset).type }}</span
    >
    <el-tag v-if="alreadyExists" type="warning" size="small"> 已在自选 </el-tag>
    <el-tag
      v-else-if="venueLabelOf(asset)"
      size="small"
      class="venue-tag"
      :class="asset.venue === 'OTC' ? 'tag-otc' : 'tag-exchange'"
    >
      {{ venueLabelOf(asset) }}
    </el-tag>
  </div>

  <dl v-if="selectedMetaRows.length" class="selected-asset-card__meta">
    <div
      v-for="row in selectedMetaRows"
      :key="row.label"
      class="selected-asset-card__meta-item"
    >
      <dt>{{ row.label }}</dt>
      <dd :title="row.value">{{ row.value }}</dd>
    </div>
  </dl>
</template>

<script setup lang="ts">
// 已选资产的「识别」区：主行（名称 · 次要锚点 · 类型配色）+ 关键信息行。
// #980 拆分自 AddToWatchlistModal.vue；**没有额外包裹元素**（多根片段），
// 与拆分前的 DOM 结构逐字一致——视觉不可能因为拆组件而变化。
import { computed } from "vue";
import { isCompositeAssetType } from "@/constants/advisorPlatform";
import { getMarketLabel } from "@/constants/market";
import {
  rowColumns,
  venueLabelOf,
  type SearchAssetOption
} from "./assetOptionColumns";

const props = defineProps<{
  asset: SearchAssetOption;
  /** 该资产已在自选列表（主行改显「已在自选」标签） */
  alreadyExists: boolean;
}>();

/**
 * 已选资产的关键信息行（信息卡内两列栅格）。
 * 组合类标的不出现「代码」行；缺失值直接过滤，避免整片「—」噪音。
 */
const selectedMetaRows = computed<{ label: string; value: string }[]>(() => {
  const item = props.asset;
  if (!item) return [];
  // 主行（rowColumns）已覆盖 名称/编码/类型（或 名称/平台/类型），
  // 此处仅补主行未承载的次要信息，避免与头部重复堆叠。
  if (isCompositeAssetType(item.type)) return [];
  const market = item.market ? getMarketLabel(item.market) : "";
  return market ? [{ label: "市场", value: market }] : [];
});
</script>

<style scoped>
.selected-asset-card__head {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.selected-asset-card__name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-body);
  font-weight: 600;
  line-height: 22px;
  color: var(--text-primary);
  white-space: nowrap;
}

.selected-asset-card__sub {
  flex: 0 0 auto;
  font-size: var(--text-label);
  line-height: 22px;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.selected-asset-card__type {
  flex-shrink: 0;
  padding: 0 6px;
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-secondary);
  background-color: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.selected-asset-card__type--fund {
  color: var(--asset-cat-fund);
  background-color: var(--asset-cat-fund-bg);
}

.selected-asset-card__type--stock {
  color: var(--asset-cat-stock);
  background-color: var(--asset-cat-stock-bg);
}

.selected-asset-card__type--etf {
  color: var(--asset-cat-etf);
  background-color: var(--asset-cat-etf-bg);
}

.selected-asset-card__type--index {
  color: var(--asset-cat-index);
  background-color: var(--asset-cat-index-bg);
}

.selected-asset-card__type--bond {
  color: var(--asset-cat-bond);
  background-color: var(--asset-cat-bond-bg);
}

.selected-asset-card__type--crypto {
  color: var(--asset-cat-crypto);
  background-color: var(--asset-cat-crypto-bg);
}

.selected-asset-card__type--portfolio {
  color: var(--asset-cat-portfolio);
  background-color: var(--asset-cat-portfolio-bg);
}

.selected-asset-card__type--manager {
  color: var(--asset-cat-manager);
  background-color: var(--asset-cat-manager-bg);
}

.selected-asset-card__type--money_fund {
  color: var(--asset-cat-money-fund);
  background-color: var(--asset-cat-money-fund-bg);
}

.selected-asset-card__type--reverse_repo {
  color: var(--asset-cat-reverse-repo);
  background-color: var(--asset-cat-reverse-repo-bg);
}

/* 关键信息两列栅格：label 弱化、value 单行省略（长公司名不撑破卡片） */
.selected-asset-card__meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 16px;
  margin-top: 10px;
}

.selected-asset-card__meta-item {
  display: flex;
  gap: 6px;
  align-items: baseline;
  min-width: 0;
  font-size: var(--text-label);
  line-height: 18px;
}

.selected-asset-card__meta-item dt {
  flex-shrink: 0;
  color: var(--text-tertiary-ink);
}

.selected-asset-card__meta-item dd {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-secondary);
  white-space: nowrap;
}

/* venue 类型标签 */
.venue-tag.tag-otc {
  color: var(--brand-700);
  background-color: var(--brand-100);
  border: none;
}

.venue-tag.tag-exchange {
  color: var(--text-secondary);
  background-color: var(--bg-soft);
  border: none;
}
</style>
