<!--
  PnlEstimateLine · 「预估」副行（#1104 抽出复用）

  为什么单独抽成一个组件：这条副行有**两个**消费方，口径与免责提示必须一致——

  1. `PnlDualLine`（全面盘点 / 账户详情 / 组合详情 / 策略分析的盈亏列）：
     主行「已确认」+ 本副行；
  2. 自选页「持仓收益」列：主行是 `MoneyWithRatio`（金额 + 百分比二合一，套不进
     `PnlDualLine`），但副行同样要「估」徽章 + 免责 tooltip。

  抽出来之前这两处只能各写一份，违反 `components.md`「禁止各页重写同类结构」。

  「估」徽章是唯一视觉锚点：`--brand-100` 底 + `--brand-700` 字 + 免责 tooltip
  （文案 `ESTIMATE_DISCLAIMER`，紧贴数字）。
-->
<template>
  <!-- 既无预估、也无提示文案 → 整行不渲染。
       自选页这种高密度表格不需要逐行复述「未开启实时估值」；
       需要复述的表格（全面盘点 / 账户详情…）由调用方传 `hint`。 -->
  <span v-if="hasEstimated || hint" class="pnl-estimate-line">
    <el-tooltip
      v-if="hasEstimated"
      :content="ESTIMATE_DISCLAIMER"
      placement="top"
    >
      <span
        class="pnl-estimate-line__badge"
        tabindex="0"
        role="note"
        :aria-label="ESTIMATE_DISCLAIMER"
        >估</span
      >
    </el-tooltip>
    <span v-else class="pnl-estimate-line__tag">预估</span>

    <MoneyDisplay
      v-if="hasEstimated"
      :value="estimated"
      :show-sign="true"
      size="xs"
    />
    <span v-else class="pnl-estimate-line__hint">{{ hint }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { ESTIMATE_DISCLAIMER } from "@/composables/usePositionValuation";

const props = withDefaults(
  defineProps<{
    /** 预估金额；`null` 表示拿不到真实行情（此时不显示数字） */
    estimated?: number | null;
    /** 拿不到预估时的提示文案；留空则整行不渲染（密集表格用） */
    hint?: string;
  }>(),
  { estimated: null, hint: "" }
);

const hasEstimated = computed(
  () => props.estimated != null && !Number.isNaN(props.estimated)
);
</script>

<style scoped>
/* inline-flex：在「右对齐的容器」里跟随文本对齐贴右缘（自选页单元格），
   在 `PnlDualLine` 的列向 flex 里则由父级 align-items: flex-end 贴右缘。 */
.pnl-estimate-line {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  line-height: 1.3;
}

/* 口径标签：次级文字色，固定 11px（副行恒比主行弱一档，不随 PnlDualLine 的 size 变） */
.pnl-estimate-line__tag {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

/* 「估」徽章：与 SegmentedControl 选中态同一「软按钮」语言（--brand-100 底 + --brand-700 字）。
   它是「这个数字不是确认值」的唯一视觉锚点，因此比旁边的口径标签更重。 */
.pnl-estimate-line__badge {
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

.pnl-estimate-line__badge:focus-visible {
  outline: 1px solid var(--brand-400);
  outline-offset: 1px;
}

/* 预估不可用时的提示：比口径标签更弱，避免在表格里抢注意力 */
.pnl-estimate-line__hint {
  font-size: 11px;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}
</style>
