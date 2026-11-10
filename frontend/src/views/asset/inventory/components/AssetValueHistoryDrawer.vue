<template>
  <el-drawer
    v-model="visible"
    :title="`${asset?.name ?? '资产'} · 变动记录`"
    size="560px"
    direction="rtl"
    destroy-on-close
  >
    <!-- 汇总层口径分叉（设计 §9.3）：单资产可回溯，家庭快照按 D62 不重算 -->
    <p class="caliber-note">
      此处为单资产历史明细；家庭净资产走势按每日落库快照生成，不会随补录改写。
    </p>

    <div v-if="loading" class="state-line">加载中…</div>
    <template v-else>
      <!-- D100：缺起账日不外推、不插值、不画 0 -->
      <p v-if="!asset?.start_date" class="gap-note">
        — 起账日未填写，历史不可回溯。仅展示已录入的变动记录。
      </p>

      <TimeSeriesChart
        v-if="categories.length"
        :categories="categories"
        :series="chartSeries"
        unit="¥"
        :height="220"
      />

      <button
        v-if="correctionCount"
        type="button"
        class="correction-toggle"
        :aria-expanded="showCorrections"
        @click="showCorrections = !showCorrections"
      >
        {{ showCorrections ? "收起" : "显示" }} {{ correctionCount }} 条更正记录
      </button>

      <ul v-if="visibleEvents.length" class="event-list">
        <li
          v-for="ev in visibleEvents"
          :key="ev.id"
          class="event-row"
          :class="{ 'is-correction': ev.kind === 'correction' }"
        >
          <div class="event-head">
            <span class="event-date">{{ formatDate(ev.effective_date) }}</span>
            <span class="event-kind">{{ kindLabel(ev.kind) }}</span>
          </div>
          <div class="event-body">
            <!-- delta 已是元，且负债方向不在事件表变号：这里不再二次取负 -->
            <MoneyDisplay :value="ev.delta" :show-sign="true" size="sm" />
            <span class="event-after">
              → 变动后 ¥{{ formatAmount(ev.value_after) }}
            </span>
          </div>
          <p v-if="ev.notes" class="event-note">{{ ev.notes }}</p>
          <p class="event-recorded">
            录入于 {{ formatDateTime(ev.recorded_at ?? "") }}
          </p>
        </li>
      </ul>
      <p v-else class="state-line">暂无变动记录</p>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
/**
 * 单资产值变动时间线抽屉（设计 §9.2 / §9.3，D99 / D100）。
 *
 * 只读：数据来自 GET /api/assets/<id>/value-events/，抽屉不写任何表。
 * 「变动后值」由后端读时折叠派生（不落库），这里只负责展示。
 * 纠错记录默认折叠、可展开（设计 §3.4）；缺起账日显示「—」而非 0 或水平线。
 */
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  getAssetValueEvents,
  type AssetRecord,
  type AssetValueEvent
} from "@/api/assets";
import TimeSeriesChart, {
  type TimeSeriesItem
} from "@/components/Charts/TimeSeriesChart.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { formatAmount } from "@/utils/currency";
import { formatDate, formatDateTime } from "@/utils/date";

const props = defineProps<{
  modelValue: boolean;
  asset: AssetRecord | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [visible: boolean];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value)
});

const loading = ref(false);
const events = ref<AssetValueEvent[]>([]);
const showCorrections = ref(false);

const KIND_LABELS: Record<string, string> = {
  valuation: "估值调整",
  repayment: "还款",
  borrow: "新增借款",
  receivable_change: "应收变动",
  correction: "更正",
  adjustment: "其他变动"
};
function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}

const valueNoun = computed(() =>
  ["liability", "receivable"].includes(props.asset?.major_category ?? "")
    ? "余额"
    : "估值"
);

async function load() {
  if (!props.asset) return;
  loading.value = true;
  try {
    const res = await getAssetValueEvents(props.asset.id, { per_page: 200 });
    events.value = res?.data ?? [];
    showCorrections.value = false;
  } catch {
    ElMessage.error("加载变动记录失败");
    events.value = [];
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.modelValue, props.asset?.id],
  ([open]) => {
    if (open) void load();
  }
);

/**
 * 折线起点 = 派生锚点（初始余额）：第一条事件的 value_after − delta。
 * 没有事件时起点就是当前 amount。start_date 为空则只画实际录入的事件点，
 * 不向前外推成水平线（D100）。
 */
const chartPoints = computed(() => {
  const points = events.value.map(ev => ({
    date: ev.effective_date,
    value: ev.value_after
  }));
  if (!props.asset?.start_date) return points;
  const initial = events.value.length
    ? events.value[0].value_after - events.value[0].delta
    : (props.asset.amount ?? 0);
  return [{ date: props.asset.start_date, value: initial }, ...points];
});

const categories = computed(() => chartPoints.value.map(p => p.date));
const chartSeries = computed<TimeSeriesItem[]>(() => [
  {
    name: valueNoun.value,
    data: chartPoints.value.map(p => p.value),
    step: "end"
  }
]);

const correctionCount = computed(
  () => events.value.filter(ev => ev.kind === "correction").length
);
/** 最新在上；更正行默认隐藏 */
const visibleEvents = computed(() =>
  [...events.value]
    .reverse()
    .filter(ev => ev.kind !== "correction" || showCorrections.value)
);
</script>

<style scoped>
.caliber-note {
  margin: 0 0 12px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  border-radius: 6px;
  color: var(--text-secondary);
  background: var(--bg-subtle);
}
.gap-note {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}
.state-line {
  padding: 16px 0;
  font-size: 13px;
  color: var(--text-tertiary-ink);
}
.correction-toggle {
  margin: 12px 0;
  padding: 4px 0;
  border: 0;
  background: none;
  font-size: 12px;
  cursor: pointer;
  color: var(--brand-600);
}
.event-list {
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}
.event-row {
  padding: 10px 0;
  border-bottom: 1px solid var(--border-default);
}
.event-row.is-correction {
  opacity: 0.72;
}
.event-head,
.event-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.event-date {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.event-kind {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  color: var(--text-secondary);
  background: var(--bg-subtle);
}
.event-after,
.event-note,
.event-recorded {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}
</style>
