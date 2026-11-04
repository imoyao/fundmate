<!--
  RoadCard · 未竟之蹊单卡

  三态（design.md 卡片规范）：
  - 浏览态：封面走势 + 标题/代码 + 持有元信息 + 笔记摘要 + 对比数据条 + 标签 + 底部复盘与操作
  - 编辑态：交给 RoadCardEditor（标签可增删 + 投资笔记 + 下次复盘日期 + 保存/取消）
  - 选中态：管理模式下勾选，--brand-700 描边 + --brand-100 底

  涨跌一律走 --color-rise / --color-fall；类型色来自 ENTITY_COLOR 令牌。

  #980 批 B6 拆分后的分工（本文件只剩「卡片外壳 + 两态切换」）：
  - 封面浮层（类型/状态/示例胶囊 + 编辑勾选）→ `RoadCardCover`
  - 三行身份信息（标题/代码/元信息）→ `RoadCardHead`
  - 对比数据条 → `RoadCardMetrics`
  - 底部复盘与操作 → `RoadCardFooter`
  - 字段解析（查表 + 兜底）→ `roadCardModel`
-->
<template>
  <article
    class="road-card"
    :class="{
      'is-selected': selected,
      'is-editing': editing,
      'is-demo': item.isDemo
    }"
    :style="{ '--card-color': color }"
    @click="onCardClick"
  >
    <RoadCardCover
      :series="item.trend"
      :color="color"
      :metric-label="metricKindLabel"
      :entity-label="entityLabel"
      :state-label="stateLabel"
      :state-style="stateChipStyle"
      :is-demo="Boolean(item.isDemo)"
      :manage-mode="Boolean(manageMode)"
      :selected="Boolean(selected)"
      @toggle-select="emit('toggle-select', item)"
      @start-edit="emit('start-edit', item)"
    />

    <div class="road-body">
      <RoadCardHead
        :title="item.display_name"
        :symbol="item.symbol"
        :venue="venueLabel"
        :asset-type="assetTypeLabel"
        :state-label="stateLabel"
        :favorite-days="favoriteDays"
        :favorite-at="item.favorite_at"
      />

      <!-- ── 浏览态 ── -->
      <template v-if="!editing">
        <p class="road-note" :class="{ 'is-empty': !item.notes_summary }">
          {{ item.notes_summary || "还没写下第一段思考。" }}
        </p>

        <RoadCardMetrics
          :metrics="metrics"
          :empty-text="emptyMetricsText(item.entity)"
        />

        <RoadTagChips :tags="tagList" />
      </template>

      <!-- ── 编辑态 ── -->
      <RoadCardEditor
        v-else
        :item="item"
        :tags="tags"
        @cancel="$emit('cancel-edit')"
        @save="draft => $emit('save', { item, draft })"
      />
    </div>

    <RoadCardFooter
      v-if="!editing"
      :review-text="reviewText"
      :is-due="isReviewDue"
      :pinned="Boolean(item.is_pinned)"
      @start-edit="emit('start-edit', item)"
      @pin="emit('pin', item)"
      @remove="emit('remove', item)"
    />
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { WatchlistTag } from "@/api/watchlist";
import type { RoadItem } from "@/types/favorites";
import RoadCardCover from "./RoadCardCover.vue";
import RoadCardHead from "./RoadCardHead.vue";
import RoadCardMetrics from "./RoadCardMetrics.vue";
import RoadCardFooter from "./RoadCardFooter.vue";
import RoadTagChips from "./RoadTagChips.vue";
import RoadCardEditor from "./RoadCardEditor.vue";
import { assetTypeLabel as assetTypeLabelFromEnum } from "@/composables/useEnumLabels";
import { cardMetrics } from "../helpers";
import {
  emptyMetricsText,
  entityColorOf,
  entityLabelOf,
  favoriteDaysOf,
  isReviewDue as isReviewDueOn,
  metricKindLabelOf,
  normalizeAssetType,
  pickTags,
  reviewTextOf,
  stateChipStyleOf,
  stateLabelOf,
  venueLabelOf
} from "./roadCardModel";

const props = defineProps<{
  item: RoadItem;
  tags: WatchlistTag[];
  selected?: boolean;
  editing?: boolean;
  manageMode?: boolean;
}>();

const emit = defineEmits<{
  (e: "toggle-select", item: RoadItem): void;
  (e: "start-edit", item: RoadItem): void;
  (e: "cancel-edit"): void;
  (
    e: "save",
    payload: {
      item: RoadItem;
      draft: {
        notes: string;
        next_review_date: string | null;
        tagIds: number[];
      };
    }
  ): void;
  (e: "pin", item: RoadItem): void;
  (e: "remove", item: RoadItem): void;
}>();

const color = computed(() => entityColorOf(props.item.entity));
const entityLabel = computed(() => entityLabelOf(props.item.entity));
const stateLabel = computed(() => stateLabelOf(props.item.holdingState));
const venueLabel = computed(() => venueLabelOf(props.item.venue));

/**
 * 资产类别中文标签。`normalizeAssetType` 先挡掉空值与 `manager`（域特有实体，
 * 卡片不显示英文原键），剩下的键交后端单一来源的标签表翻译。
 */
const assetTypeLabel = computed(() => {
  const at = normalizeAssetType(props.item.asset_type);
  return at ? assetTypeLabelFromEnum(at) : "";
});

const metricKindLabel = computed(() => metricKindLabelOf(props.item.entity));
const favoriteDays = computed(() => favoriteDaysOf(props.item.favorite_at));
const metrics = computed(() => cardMetrics(props.item));

/** 状态胶囊配色（语义色，非涨跌） */
const stateChipStyle = computed(() =>
  stateChipStyleOf(props.item.holdingState)
);

const tagList = computed<WatchlistTag[]>(() =>
  pickTags(props.item.tag_ids ?? [], props.tags)
);

const reviewText = computed(() => reviewTextOf(props.item.next_review_date));
const isReviewDue = computed(() => isReviewDueOn(props.item.next_review_date));

function onCardClick() {
  if (props.manageMode) emit("toggle-select", props.item);
}
</script>

<style scoped>
.road-card {
  overflow: hidden;
  cursor: default;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  transition:
    transform 0.22s cubic-bezier(0.4, 0, 0.2, 1),
    box-shadow 0.22s cubic-bezier(0.4, 0, 0.2, 1),
    border-color 0.22s ease;
}

/* Hover 态：轻微上浮 + 品牌描边（--brand-400 软强调，非涨跌语义） */
.road-card:hover {
  border-color: var(--brand-400);
  box-shadow: var(--shadow-float);
  transform: translateY(-3px);
}

/* 选中态 */
.road-card.is-selected {
  background: var(--brand-100);
  border-color: var(--brand-700);
}

.road-card.is-demo {
  border-style: dashed;
}

.road-card.is-editing {
  border-color: var(--brand-400);
}

/* 编辑入口的显示条件：`.road-edit-entry` 在 `RoadCardCover` 内，祖先选择器
   跨 scoped 块只能靠 `:deep()` 穿透（子组件自己只管 opacity:0 基态与
   focus-visible / 无 hover 设备这两条自洽规则）。
   键盘焦点与触屏（无 hover）也要能看到操作入口（#1834）：原来只有 :hover，
   触屏设备与键盘用户永远看不到这个编辑入口——功能等于不存在 */
.road-card:hover :deep(.road-edit-entry),
.road-card:focus-within :deep(.road-edit-entry) {
  opacity: 1;
}

/* ── 正文 ── */
.road-body {
  padding: 14px 16px 12px;
}

.road-note {
  display: -webkit-box;
  margin-top: 10px;
  overflow: hidden;
  -webkit-line-clamp: 3;
  font-size: var(--text-label);
  line-height: 1.65;
  color: var(--text-secondary);
  -webkit-box-orient: vertical;
}

.road-note.is-empty {
  font-style: italic;
  color: var(--text-tertiary-ink);
}
</style>
