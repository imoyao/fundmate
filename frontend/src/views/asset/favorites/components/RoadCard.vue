<!--
  RoadCard · 未竟之蹊单卡

  三态（design.md 卡片规范）：
  - 浏览态：封面走势 + 标题/代码 + 持有元信息 + 笔记摘要 + 对比数据条 + 标签 + 底部复盘与操作
  - 编辑态：交给 RoadCardEditor（标签可增删 + 投资笔记 + 下次复盘日期 + 保存/取消）
  - 选中态：管理模式下勾选，--brand-700 描边 + --brand-100 底

  涨跌一律走 --color-rise / --color-fall；类型色来自 ENTITY_COLOR 令牌。
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
    <!-- 封面：走势缩略图 + 类型/状态胶囊 + 编辑/勾选入口 -->
    <RoadSparkline :series="item.trend" :color="color" :metric-label="metricKindLabel">
      <span class="road-chip road-chip--type">{{ entityLabel }}</span>
      <span class="road-chip road-chip--state" :style="stateChipStyle">
        {{ stateLabel }}
      </span>
      <span v-if="item.isDemo" class="road-chip road-chip--demo">示例</span>

      <button
        v-if="manageMode"
        type="button"
        class="road-check"
        :class="{ 'is-on': selected }"
        :aria-label="selected ? '取消选择' : '选择该卡片'"
        @click.stop="$emit('toggle-select', item)"
      >
        <IconifyIconOffline v-if="selected" icon="ep:check" />
      </button>
      <button
        v-else
        type="button"
        class="road-edit-entry"
        aria-label="编辑这张卡片"
        @click.stop="$emit('start-edit', item)"
      >
        <IconifyIconOffline icon="ep:edit-pen" />
      </button>
    </RoadSparkline>

    <div class="road-body">
      <h3 class="road-title" :title="item.display_name">
        {{ item.display_name }}
      </h3>
      <p class="road-code">
        {{ item.symbol }}
        <template v-if="venueLabel"> · {{ venueLabel }}</template>
        <template v-if="assetTypeLabel"> · {{ assetTypeLabel }}</template>
      </p>
      <p class="road-meta">
        <span>{{ stateLabel }}</span>
        <template v-if="favoriteDays != null">
          · 关注 {{ favoriteDays }} 天</template
        >
        <template v-if="item.favorite_at">
          · 标记于 {{ item.favorite_at }}</template
        >
      </p>

      <!-- ── 浏览态 ── -->
      <template v-if="!editing">
        <p class="road-note" :class="{ 'is-empty': !item.notes_summary }">
          {{ item.notes_summary || "还没写下第一段思考。" }}
        </p>

        <div v-if="metrics.length" class="road-metrics">
          <div
            v-for="metric in metrics"
            :key="metric.label"
            class="road-metric"
          >
            <span class="road-metric__label">{{ metric.label }}</span>
            <span
              class="road-metric__value"
              :style="{ color: pctColorVar(metric.value) }"
              >{{ pctText(metric.value) }}</span
            >
          </div>
        </div>
        <p v-else class="road-metrics road-metrics--empty">
          {{
            item.entity === "manager" ? "经理生涯数据接入中" : "行情数据积累中"
          }}
        </p>

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

    <!-- 底部：复盘提醒 + 互动操作 -->
    <footer v-if="!editing" class="road-footer" @click.stop>
      <span class="road-review" :class="{ 'is-due': isReviewDue }">
        <IconifyIconOffline icon="ep:alarm-clock" />
        {{ reviewText || "还没定复盘日期" }}
      </span>
      <div class="road-ops">
        <button
          type="button"
          class="road-op"
          title="写笔记"
          @click="$emit('start-edit', item)"
        >
          <IconifyIconOffline icon="ep:edit-pen" />
        </button>
        <button
          type="button"
          class="road-op"
          :class="{ 'is-on': item.is_pinned }"
          title="置顶"
          @click="$emit('pin', item)"
        >
          <IconifyIconOffline
            :icon="item.is_pinned ? 'ep:star-filled' : 'ep:star'"
          />
        </button>
        <button
          type="button"
          class="road-op road-op--danger"
          title="移出特别关注"
          @click="$emit('remove', item)"
        >
          <IconifyIconOffline icon="ep:remove" />
        </button>
      </div>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import type { WatchlistTag } from "@/api/watchlist";
import type { RoadItem } from "@/types/favorites";
import RoadSparkline from "./RoadSparkline.vue";
import RoadTagChips from "./RoadTagChips.vue";
import RoadCardEditor from "./RoadCardEditor.vue";
import {
  ENTITY_COLOR,
  ENTITY_LABEL,
  HOLDING_STATE_LABEL,
  VENUE_LABEL
} from "../constants";
import { assetTypeLabel as assetTypeLabelFromEnum } from "@/composables/useEnumLabels";
import {
  cardMetrics,
  daysBetween,
  daysFromToday,
  pctColorVar,
  pctText,
  reviewHintText
} from "../helpers";

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

const color = computed(
  () => ENTITY_COLOR[props.item.entity] || "var(--text-tertiary)"
);
const entityLabel = computed(() => ENTITY_LABEL[props.item.entity] ?? "资产");
const stateLabel = computed(
  () => HOLDING_STATE_LABEL[props.item.holdingState] ?? "观察中"
);
const venueLabel = computed(() =>
  props.item.venue ? (VENUE_LABEL[props.item.venue] ?? props.item.venue) : ""
);
const assetTypeLabel = computed(() => {
  const at = props.item.asset_type?.toLowerCase();
  // manager 为域特有实体（非通用 asset_type），卡片不显示英文原键；其余走后端单一来源标签
  if (!at || at === "manager") return "";
  return assetTypeLabelFromEnum(at);
});
/** 封面走势的口径标注：基金画净值、指数画点位、股票画价格；经理无曲线不标注 */
const metricKindLabel = computed(() => {
  switch (props.item.entity) {
    case "fund":
      return "净值";
    case "index":
      return "点位";
    case "stock":
      return "价格";
    default:
      return "";
  }
});
const favoriteDays = computed(() => daysBetween(props.item.favorite_at));
const metrics = computed(() => cardMetrics(props.item));

/** 状态胶囊配色（语义色，非涨跌） */
const stateChipStyle = computed(() => {
  const map: Record<string, { bg: string; fg: string }> = {
    holding: { bg: "var(--brand-100)", fg: "var(--brand-700)" },
    watching: { bg: "var(--bg-soft)", fg: "var(--text-secondary)" },
    cleared: { bg: "var(--color-warning-20)", fg: "var(--text-secondary)" }
  };
  const tone = map[props.item.holdingState] ?? map.watching;
  return { backgroundColor: tone.bg, color: tone.fg };
});

const tagList = computed<WatchlistTag[]>(() =>
  props.item.tag_ids
    .map(id => props.tags.find(t => t.id === id))
    .filter((t): t is WatchlistTag => Boolean(t))
);

const reviewText = computed(() => reviewHintText(props.item.next_review_date));
const isReviewDue = computed(() => {
  const days = daysFromToday(props.item.next_review_date);
  return days != null && days <= 7;
});

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

/* ── 封面胶囊 ── */
.road-chip {
  position: absolute;
  padding: 2px 8px;
  font-size: 11px;
  line-height: 18px;
  white-space: nowrap;
  border-radius: var(--radius-pill);
}

.road-chip--type {
  top: 10px;
  left: 10px;
  color: var(--bg-card);
  background: var(--card-color);
}

.road-chip--state {
  top: 10px;
  right: 10px;
}

.road-chip--demo {
  right: 10px;
  bottom: 10px;
  color: var(--text-secondary);
  background: var(--glass-bg);
  border: 1px solid var(--border-default);
}

.road-check {
  position: absolute;
  right: 10px;
  bottom: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  color: var(--text-tertiary);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 50%;
}

.road-check.is-on {
  color: var(--bg-card);
  background: var(--brand-700);
  border-color: var(--brand-700);
}

.road-edit-entry {
  position: absolute;
  right: 10px;
  bottom: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--glass-bg);
  border-radius: 50%;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.road-card:hover .road-edit-entry {
  opacity: 1;
}

/* ── 正文 ── */
.road-body {
  padding: 14px 16px 12px;
}

.road-title {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-primary);
  white-space: nowrap;
}

.road-code {
  margin-top: 2px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

.road-meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.road-note {
  display: -webkit-box;
  margin-top: 10px;
  overflow: hidden;
  -webkit-line-clamp: 3;
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-secondary);
  -webkit-box-orient: vertical;
}

.road-note.is-empty {
  font-style: italic;
  color: var(--text-tertiary);
}

/* 对比数据条 */
.road-metrics {
  display: flex;
  gap: 14px;
  margin-top: 12px;
}

.road-metrics--empty {
  font-size: 12px;
  color: var(--text-tertiary);
}

.road-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.road-metric__label {
  font-size: 11px;
  color: var(--text-tertiary);
}

.road-metric__value {
  font-family: var(--font-mono, monospace);
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* ── 底部互动行 ── */
.road-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-top: 1px solid var(--border-subtle);
}

.road-review {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  font-size: 12px;
  color: var(--text-tertiary);
}

.road-review.is-due {
  color: var(--brand-700);
}

.road-ops {
  display: inline-flex;
  gap: 2px;
}

.road-op {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  font-size: 14px;
  color: var(--text-tertiary);
  border-radius: 50%;
  transition:
    color 0.15s ease,
    background-color 0.15s ease;
}

.road-op:hover {
  color: var(--brand-700);
  background: var(--brand-100);
}

.road-op.is-on {
  color: var(--brand-700);
}

.road-op--danger:hover {
  color: var(--color-danger-system);
  background: var(--color-danger-20);
}
</style>
