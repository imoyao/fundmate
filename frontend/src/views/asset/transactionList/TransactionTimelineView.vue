<script setup lang="ts">
// 交易流水 · 流水线视图（**按月**分组，月内一行一笔）。行的渲染在 `TransactionTimelineRow`。
//
// 设计 §五：桌面上一日通常只有一两笔，按日分组就是一屏空折叠头，节奏感被切碎。
// 月头 sticky + 月内合计（笔数 / 买入 / 卖出 / 净额），默认展开最近**两个有记录的**月。
//
// 滚动懒加载收在组件内部：容器随视图挂载/卸载，用模板 `@scroll` 就自动跟着生命周期走，
// 不必像原来那样在父层手动 addEventListener + watch(viewMode) 解绑重绑。
import { computed, ref, watch } from "vue";
import type { TransactionRecord } from "@/api/transactions";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import TransactionTimelineRow from "./TransactionTimelineRow.vue";
import {
  groupByMonth,
  resolveOpenMonths,
  type MonthGroup
} from "./transactionListModel";

const props = defineProps<{
  transactions: TransactionRecord[];
  loading: boolean;
  loadingMore: boolean;
  hasMore: boolean;
}>();

const emit = defineEmits<{ edit: [row: any]; "load-more": [] }>();

const openMonths = ref<string[]>([]);
const scrollEl = ref<HTMLElement | null>(null);
/** 上一次首条 id：用于在「重置」（首条变了 / 长度变短）时回到默认展开，而非「加载更多」（追加）。 */
const prevFirstId = ref<number | null>(null);

const groups = computed(() => groupByMonth(props.transactions));

/**
 * 展开态：首次进入或**重置**（换筛选）回到「最近两月」；**加载更多**（追加同月数据）
 * 保留用户手动展开 / 折叠的状态——否则滑到底触发加载，刚才展开的那个月会被重新折叠，
 * 看起来就像「月份没了 / 数据没更新」（v1.3 修的感知 bug）。
 */
watch(
  () => props.transactions,
  (next, prev) => {
    const firstId = next[0]?.id ?? null;
    const isReset =
      !prev ||
      prev.length === 0 ||
      next.length < prev.length ||
      firstId !== prevFirstId.value;
    openMonths.value = resolveOpenMonths(
      openMonths.value,
      groups.value,
      isReset
    );
    prevFirstId.value = firstId;
  },
  { immediate: true, flush: "post" }
);

function isOpen(month: string): boolean {
  return openMonths.value.includes(month);
}

function toggle(month: string) {
  openMonths.value = isOpen(month)
    ? openMonths.value.filter(item => item !== month)
    : [...openMonths.value, month];
}

function sectionId(group: MonthGroup): string {
  return `txn-month-${group.month || "unknown"}`;
}

/** 触底 100px 内加载下一页 */
function onScroll() {
  const el = scrollEl.value;
  if (!el || props.loadingMore || !props.hasMore) return;
  if (el.scrollTop + el.clientHeight + 100 >= el.scrollHeight) {
    emit("load-more");
  }
}
</script>

<template>
  <div
    ref="scrollEl"
    v-loading="loading"
    class="txn-timeline"
    @scroll="onScroll"
  >
    <!-- 空状态 -->
    <div
      v-if="transactions.length === 0 && !loading"
      class="txn-timeline__empty"
    >
      <IconifyIconOffline icon="ep:folder-opened" class="text-4xl mb-2" />
      <p>没有符合条件的流水</p>
      <p class="txn-timeline__empty-hint">
        当前筛选下没有任何记录。放宽时间范围，或清空筛选重新看。
      </p>
    </div>

    <section v-for="group in groups" :key="group.month || 'unknown'">
      <!-- 月头：sticky，点整行折叠。用原生 button 而不是 div＋@click——可聚焦、可回车、
           读屏能播报 aria-expanded，这三点加一堆兜底属性才追得上按钮。 -->
      <button
        type="button"
        class="txn-month__head"
        :aria-expanded="isOpen(group.month)"
        :aria-controls="sectionId(group)"
        @click="toggle(group.month)"
      >
        <span class="txn-month__label">{{ group.label }}</span>
        <span class="txn-month__summary">
          <span>{{ group.summary.count }} 笔</span>
          <span class="txn-month__metric">
            买入
            <MoneyDisplay
              :value="group.summary.buy"
              :show-sign="false"
              :auto-color="false"
              size="xs"
            />
          </span>
          <span class="txn-month__metric">
            卖出
            <MoneyDisplay
              :value="group.summary.sell"
              :show-sign="false"
              :auto-color="false"
              size="xs"
            />
          </span>
          <span class="txn-month__metric">
            净额
            <MoneyDisplay
              :value="group.summary.net"
              :auto-color="false"
              size="xs"
            />
          </span>
        </span>
        <span class="txn-month__caret" aria-hidden="true" />
      </button>

      <ul
        v-show="isOpen(group.month)"
        :id="sectionId(group)"
        class="txn-month__body"
      >
        <TransactionTimelineRow
          v-for="txn in group.records"
          :key="txn.id"
          :txn="txn"
          @edit="emit('edit', $event)"
        />
      </ul>
    </section>

    <!-- 加载更多提示：loadingMore 时给出明确的旋转 + 文案，给「无限加载」的视觉反馈；
         否则只放一行静态提示，用户触底后看不到任何动静，会以为卡了 / 数据没更新。 -->
    <div
      v-if="hasMore"
      class="txn-timeline__more"
      :class="{ 'txn-timeline__more--loading': loadingMore }"
      aria-live="polite"
    >
      <span
        v-if="loadingMore"
        class="txn-timeline__spinner"
        aria-hidden="true"
      />
      <span>{{ loadingMore ? "加载中…" : "下滑加载更多数据" }}</span>
    </div>
    <div v-else-if="transactions.length > 0" class="txn-timeline__end">
      已经到底了
    </div>
  </div>
</template>

<style scoped>
.txn-timeline {
  max-height: 75vh;
  padding: var(--space-1) 0 var(--space-3);
  overflow-y: auto;
}

.txn-timeline__empty {
  padding: var(--space-section) 0;
  color: var(--text-tertiary-ink);
  text-align: center;
}

.txn-timeline__empty-hint {
  margin-top: 4px;
  font-size: var(--text-label);
}

.txn-timeline__more {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  padding: var(--space-4) 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;
}

/* 旋转环：纯 CSS，不用图标字体（emoji / 图标字体当 loading 是明令禁止的）。
   给「无限加载」明确的视觉反馈——否则触底后没动静会像卡死。 */
.txn-timeline__spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-light);
  border-top-color: var(--color-primary-ink);
  border-radius: 50%;
  animation: txn-spin 0.7s linear infinite;
}

.txn-timeline__end {
  padding: var(--space-4) 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;
}

@keyframes txn-spin {
  to {
    transform: rotate(360deg);
  }
}

.txn-month + .txn-month {
  margin-top: var(--space-1);
  border-top: 1px solid var(--border-light);
}

/* 月头 sticky：滚动时当前月始终可见，回答「我现在看的是哪个月」 */
.txn-month__head {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
  width: 100%;
  padding: 12px var(--space-compact);
  font: inherit;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  background: var(--bg-page);
  border: none;
  border-bottom: 1px solid var(--border-light);
}

.txn-month__head:hover {
  background: var(--bg-soft);
}

.txn-month__head:focus-visible {
  outline: 2px solid var(--color-primary-ink);
  outline-offset: -2px;
}

.txn-month__label {
  flex: none;
  font-size: var(--text-small);
  font-weight: 600;
}

.txn-month__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.txn-month__metric {
  display: inline-flex;
  gap: 4px;
  align-items: baseline;
}

/* 折叠指示：纯 CSS 三角，不用图标字体（emoji 当图标是明令禁止的）。 */
.txn-month__caret {
  width: 0;
  height: 0;
  margin-left: auto;
  border-top: 5px solid var(--text-tertiary-ink);
  border-right: 4px solid transparent;
  border-left: 4px solid transparent;
  transition: transform 200ms ease-out;
}

.txn-month__head[aria-expanded="false"] .txn-month__caret {
  transform: rotate(-90deg);
}

.txn-month__body {
  padding: 0 0 var(--space-1);
  margin: 0;
  list-style: none;
}

/* 减少动效偏好：压到 0.01ms 而不是删掉过渡——直接删会让状态切换在某些浏览器里跳变 */
@media (prefers-reduced-motion: reduce) {
  .txn-month__caret {
    transition-duration: 0.01ms;
  }

  .txn-timeline__spinner {
    animation-duration: 0.01ms;
  }
}
</style>
