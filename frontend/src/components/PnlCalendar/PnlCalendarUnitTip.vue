<!--
  PnlCalendarUnitTip · 「一个格子」的悬浮卡片（#1942 第三轮反馈）

  为什么要有这个组件：原先格子的提示是**浏览器原生 `title`**——延迟约 1 秒、
  样式完全不可控（跟着系统主题走）、窄屏直接截断，而且只能放一行纯文本。
  用户的原话是「这个 hover 似乎有点太没有设计感了」。

  现在的分工：
    悬停卡片    日期（含星期）＋ 金额与收益率**同显** ＋ 一句话说清这个状态
    aria-label  仍走 `stateDescription()`（一行读完，读屏不依赖浮层）

  内容结构（一行一件事，扫读友好）：
    2026 年 9 月 15 日 · 周二
    -3,488.97 元   -1.09%
    部分标的未更新估值：数字可信，但不完整

  **金额与收益率同显**是有意的：卡片不跟随「金额 / 收益率」开关——悬停本来
  就是「我想多看一眼这个格子」，两个口径都给出比只给一个更有用。
-->

<template>
  <div class="pnl-tip">
    <div class="pnl-tip__head">{{ head }}</div>
    <div v-if="hasValue" class="pnl-tip__values">
      <MoneyDisplay :value="pnl" size="sm" :show-currency="true" />
      <RiseFallText v-if="rate !== null" :value="rate" size="sm" />
      <!-- 收益率不可算（缺前一日基准）：说清原因，不写 0.00% -->
      <span v-else class="pnl-tip__none">收益率 —</span>
    </div>
    <div v-else class="pnl-tip__values">
      <span class="pnl-tip__tag">{{ stateTag(state) }}</span>
    </div>
    <div v-if="note" class="pnl-tip__note">{{ note }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import type { PnlCalendarState } from "@/api/summary";
import {
  hasValueState,
  readableName,
  stateNote,
  stateTag,
  weekdayName
} from "./helpers";

defineOptions({ name: "PnlCalendarUnitTip" });

const props = withDefaults(
  defineProps<{
    /** 单元键：日 `YYYY-MM-DD` / 月 `YYYY-MM` / 年 `YYYY`（键长即粒度） */
    name: string;
    state: PnlCalendarState;
    pnl: number | null;
    rate?: number | null;
  }>(),
  { rate: null }
);

/** 标题行：期间名 + 星期（只有日粒度有星期） */
const head = computed(() => {
  const label = readableName(props.name);
  const week = weekdayName(props.name);
  return week ? `${label} · ${week}` : label;
});

const hasValue = computed(() => hasValueState(props.state));

const note = computed(() => stateNote(props.state));
</script>

<style scoped>
.pnl-tip {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pnl-tip__head {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.pnl-tip__values {
  display: flex;
  gap: 10px;
  align-items: baseline;
}

/* 收益率不可算 / 非盈亏态：与正文同级但更轻，不抢数字的位置 */
.pnl-tip__none,
.pnl-tip__tag {
  font-size: 12px;
  color: var(--text-secondary);
}

.pnl-tip__note {
  max-width: 260px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
}
</style>
