<script setup lang="ts">
import { computed } from "vue";
import {
  otherSortMetric,
  sortMetricSymbol,
  type SortMetric
} from "@/views/asset/watchlist/sortMetric";

/**
 * 复合列列头（2026-10-30 二次优化，取代 `DayPnlSortHeader.vue`）。
 *
 * ## 它解决什么
 *
 * 自选表里有三个复合列（当日盈亏 / 持仓市值 / 持仓收益），每列都是「金额 + 比例」
 * 两行数，两行各自可排序。首版把口径藏在列头的小箭头下拉里：**不点开就不知道
 * 当前按哪一档排**，而且切一次要点两次（展开 → 选）。用户原话：口径状态要常驻可见，
 * 升降序切换要少点几次。
 *
 * 现在：
 * 1. **口径常驻**：列名右边一枚小徽标，永远显示当前口径（`¥` = 金额 / `%` = 比例）。
 * 2. **一点即切**：点徽标 = 切口径 + 按新口径重排，没有下拉层级。
 * 3. **方向一点即转**：复合列的 `sortOrders` 只有两档（见 `ColumnDef.sortOrders`），
 *    点列名本体每次都是换方向，不再经过「取消」那一档。
 *
 * ## 为什么是 `¥` / `%` 两个字宽而不是「金额 / 涨幅」
 *
 * 列宽是硬约束：`当日盈亏` 只有 104px（默认列预算 1040 已用满 1036，见
 * `columnDefs.ts` 铁律 1），列名 56px + 排序三角 18px + 内边距 8px 之后只剩约 20px。
 * 一个符号刚好放下，两个汉字会把列名或排序三角挤出去（裁掉三角 = 点不到）。
 * 语义交给 `title` / `aria-label`（含完整文案与「点一下切成什么」）。
 */
const props = defineProps<{
  /** 列名（与 `ColumnDef.label` 一致） */
  label: string;
  /** 当前口径 */
  metric: SortMetric;
  /** 两个口径在本列的叫法（当日盈亏是「金额/涨幅」，持仓收益是「金额/收益率」） */
  labels: { amount: string; ratio: string };
}>();

const emit = defineEmits<{ (e: "change", metric: SortMetric): void }>();

const currentLabel = computed(() => props.labels[props.metric]);
const nextMetric = computed(() => otherSortMetric(props.metric));
const nextLabel = computed(() => props.labels[nextMetric.value]);
const hint = computed(
  () =>
    `排序口径：${currentLabel.value}（点 ${sortMetricSymbol(nextMetric.value)} 改为按${nextLabel.value}排）`
);

function toggle() {
  emit("change", nextMetric.value);
}
</script>

<template>
  <span class="csh">
    <!-- 列名本体的点击交给 el-table（换升/降序）——不要在这里 stop，否则排序失效；
         长列名在极窄列上省略，保证排序三角与徽标不被挤出列宽 -->
    <span class="csh__label">{{ label }}</span>
    <button
      type="button"
      class="csh__metric"
      :class="{ 'is-ratio': metric === 'ratio' }"
      :title="hint"
      :aria-label="hint"
      @click.stop="toggle"
    >
      {{ sortMetricSymbol(metric) }}
    </button>
  </span>
</template>

<style scoped>
.csh {
  display: inline-flex;
  gap: 2px;
  align-items: center;

  /* 列宽紧张时（当日盈亏 104px）允许列名省略，徽标与排序三角优先保住 */
  min-width: 0;
  max-width: 100%;
}

.csh__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 徽标：默认中性（金额），切到比例时用品牌色——「颜色变了」本身就是口径已切换的信号。
   字号走令牌（`--text-label`，13px = 设计系统下限，全仓禁裸 px：stylelint 的
   declaration-property-value-disallowed-list）；「比列名小一档」的观感靠 1px 边框 +
   15px 行高 + 品牌色区分，不靠再压字号。 */
.csh__metric {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  min-width: 15px;
  height: 16px;
  padding: 0 2px;
  font-size: var(--text-label);
  font-weight: 600;
  line-height: 1;
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 3px;
  transition:
    color 150ms ease,
    border-color 150ms ease;
}

.csh__metric.is-ratio {
  color: var(--brand-ink);
  background: var(--brand-100);
  border-color: var(--brand-200);
}

.csh__metric:hover {
  color: var(--brand-ink);
  border-color: var(--brand-ink);
}

.csh__metric:focus-visible {
  outline: 2px solid var(--brand-ink);
  outline-offset: 1px;
}
</style>
