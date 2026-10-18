<!--
  ValuationSourceBadge · 「估 / 确认」状态徽标（#2143 统一实现）

  为什么抽成组件：估值状态徽标此前散落在盈亏副行（PnlEstimateLine 手写「估」胶囊）
  与收益日历（无标记）两处，口径与视觉要长期一致，只能有一个实现
  （`docs/design/components.md`「禁止各页重写同类结构」）。

  三要素契约（卡面要求）：状态 + 来源 + 数据时间。
    - 状态：`status` prop（后端字段契约 estimated / confirmed），**禁止前端按日期推断**；
      未知状态整块不渲染——没有状态就不画，不猜。
    - 来源 / 数据时间：`source` / `sourceTime` prop，拼进 aria 与调用方 tip，
      映射表见同目录 helpers.ts（单一出口，新源只加一行）。

  视觉（design.md「Badge / Tag」）：
    - estimated → --brand-100 底 + --brand-700 字（沿用 #1104 既有「估」胶囊，
      「这个数字不是确认值」的唯一视觉锚点，比口径标签重一档）；
    - confirmed → --bg-soft 底 + --text-secondary 字（设计系统默认徽章档：
      已确认是「尘埃落定」的安静态，让数字本身承载注意力）；
    - 红绿是涨跌语义专用，本组件两态都不碰。

  提示语归调用方：本组件**不内置 el-tooltip**——
    - 盘中副行：PnlEstimateLine 外套 tooltip（文案 ESTIMATE_DISCLAIMER 单一出口）；
    - 日历格：外层已有整格悬浮卡（PnlCalendarUnitTip），内嵌 tooltip 会双层打架，
      说明写进悬浮卡；徽标自身以 role="note" + aria-label 保证读屏与键盘可达。
-->
<template>
  <span
    v-if="label"
    class="val-src-badge"
    :class="[`val-src-badge--${status}`, `val-src-badge--${size}`]"
    tabindex="0"
    role="note"
    :aria-label="aria"
    >{{ label }}</span
  >
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  valuationDefaultAria,
  valuationMetaText,
  valuationStatusLabel
} from "./helpers";

defineOptions({ name: "ValuationSourceBadge" });

const props = withDefaults(
  defineProps<{
    /** 状态（后端字段契约：estimated / confirmed）；未知值整块不渲染 */
    status?: string | null;
    /** 来源标识（后端 source 或前端 Quote.provider）；拼入提示，不单独占位 */
    source?: string | null;
    /** 源端数据时间字符串（原样展示，不在前端解析） */
    sourceTime?: string | null;
    /** 完整提示文案：各语境说法不同由调用方传（盘中免责 / 日历定格说明） */
    tip?: string | null;
    /** md＝16px（盈亏副行既有规格）；sm＝14px（日历格密排） */
    size?: "md" | "sm";
  }>(),
  {
    status: null,
    source: null,
    sourceTime: null,
    tip: null,
    size: "md"
  }
);

const label = computed(() => valuationStatusLabel(props.status));

/** 读屏文案 = 调用方 tip（缺省为状态短语）+ 元信息，一行读全「是什么 · 哪来的 · 几点的」 */
const aria = computed(() => {
  const base = props.tip || valuationDefaultAria(props.status);
  const meta = valuationMetaText(props.source, props.sourceTime);
  return meta ? `${base}（${meta}）` : base;
});
</script>

<style scoped>
/* 几何与 #1104 既有「估」胶囊逐像素一致（md），sm 档等比收紧给日历格用 */
.val-src-badge {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: var(--text-label);
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  cursor: help;
  border-radius: var(--radius-pill);
}

.val-src-badge--sm {
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  font-size: var(--text-label);
}

/* 预估：品牌软按钮语言（与 SegmentedControl 选中态同族）——「非确认值」的警示锚点 */
.val-src-badge--estimated {
  color: var(--brand-700);
  background-color: var(--brand-100);
}

/* 已确认：设计系统默认徽章档（design.md「Badge / Tag」默认行）——安静、不抢数字 */
.val-src-badge--confirmed {
  color: var(--text-secondary);
  background-color: var(--bg-soft);
}

.val-src-badge:focus-visible {
  outline: 1px solid var(--brand-400);
  outline-offset: 1px;
}
</style>
