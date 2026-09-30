<!--
  PnlDualLine · 盈亏双线（设计系统组件，#1104）

  两行同显，口径必须可辨：
  - 主行「已确认」：T-1 确认净值 / 最近交易日收盘价口径（后端权威值，可复算）；
  - 副行「预估」：盘中实时行情估算口径，带「估」标记 + 免责 tooltip，用户可感知。

  为什么不做成「切换」而是「同显」：切换只能看到一个数，用户无从判断
  「我现在看到的是确认值还是估值」；同显时两条线的差异本身就是信息
  （盘中估值相对确认净值的偏移）。切换器由调用方按需另行提供。

  纯展示组件：不取数、不推断口径，两个值由调用方（`usePositionValuation`）传入。
-->
<template>
  <div class="pnl-dual-line" :class="`pnl-dual-line--${size}`">
    <!-- 主行：已确认（权威口径） -->
    <div class="pnl-dual-line__row">
      <span class="pnl-dual-line__tag">已确认</span>
      <MoneyDisplay
        :value="confirmed"
        :show-sign="true"
        :size="size"
        empty-text="--"
      />
    </div>

    <!-- 副行：当日预估（估值口径）。拿到真实行情才显示数字 -->
    <div class="pnl-dual-line__row">
      <el-tooltip
        v-if="hasEstimated"
        :content="ESTIMATE_DISCLAIMER"
        placement="top"
      >
        <span
          class="pnl-dual-line__badge"
          tabindex="0"
          role="note"
          :aria-label="ESTIMATE_DISCLAIMER"
          >估</span
        >
      </el-tooltip>
      <span v-else class="pnl-dual-line__tag">预估</span>

      <MoneyDisplay
        v-if="hasEstimated"
        :value="estimated"
        :show-sign="true"
        size="xs"
      />
      <span v-else class="pnl-dual-line__hint">{{ hint }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { ESTIMATE_DISCLAIMER } from "@/composables/usePositionValuation";

const props = withDefaults(
  defineProps<{
    /** 已确认盈亏（T-1 口径）；null / undefined 渲染为 `--` */
    confirmed?: number | null;
    /** 当日预估盈亏（估值口径）；null 表示拿不到真实行情，此时不显示数字 */
    estimated?: number | null;
    /** 预估不可用时的副行提示（由调用方按原因给出，见 usePositionValuation.estimateHint） */
    hint?: string;
    /** 主行金额字号；副行恒为 xs（维持主次层级） */
    size?: "sm" | "md";
  }>(),
  { confirmed: null, estimated: null, hint: "", size: "sm" }
);

const hasEstimated = computed(
  () => props.estimated != null && !Number.isNaN(props.estimated)
);
</script>

<style scoped>
/* 右对齐堆叠：金额始终贴右缘，两行数字天然对齐，便于纵向扫读 */
.pnl-dual-line {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-end;
  line-height: 1.3;
}

.pnl-dual-line__row {
  display: flex;
  gap: 6px;
  align-items: baseline;
}

/* 口径标签：次级文字色，字号随档位（11/12px），不参与涨跌着色 */
.pnl-dual-line__tag {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.pnl-dual-line--md .pnl-dual-line__tag {
  font-size: 12px;
}

/* 「估」徽章：与 SegmentedControl 选中态同一「软按钮」语言（--brand-100 底 + --brand-700 字）。
   它是「这个数字不是确认值」的唯一视觉锚点，因此比旁边的口径标签更重。 */
.pnl-dual-line__badge {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  color: var(--brand-700);
  cursor: help;
  background-color: var(--brand-100);
  border-radius: var(--radius-pill);
}

.pnl-dual-line__badge:focus-visible {
  outline: 1px solid var(--brand-400);
  outline-offset: 1px;
}

/* 预估不可用时的提示：比口径标签更弱，避免在表格里抢注意力 */
.pnl-dual-line__hint {
  font-size: 11px;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}
</style>
