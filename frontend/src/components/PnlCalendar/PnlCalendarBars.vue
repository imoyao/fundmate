<!--
  PnlCalendarBars · 收益日历的「柱状图」视图（#1812）

  从 PnlCalendar 拆出（父组件 640 行超`check_vue_size.mjs` 的 400 行软阈值）。
  拆分理由不是「凑行数」：柱状图与日历图是**两种呈现角度**，
  日历回答「哪几天」，柱状回答「月内起伏」，各自的数据整形逻辑也不同
  （柱状要算零轴上下半区的高度百分比，日历要算色深档位）。

  柱状图粒度 = **月内逐日**（非年级的月度）。若做年级会与复盘页重复，
  且失去「看月内起伏」的意义（见设计文档 §4.3）。
-->

<template>
  <div class="pnl-calendar-bars" role="img" :aria-label="ariaLabel">
    <div
      v-for="bar in bars"
      :key="bar.key"
      class="pnl-calendar-bars__slot"
      :title="bar.title"
    >
      <div class="pnl-calendar-bars__track">
        <div class="pnl-calendar-bars__bar" :style="bar.style" />
      </div>
      <span class="pnl-calendar-bars__label">{{ bar.day }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { PnlCalendarDay, PnlCalendarState } from "@/api/summary";

defineOptions({ name: "PnlCalendarBars" });

// 三个 prop 都由父组件必传，故不给 withDefaults 默认值——
// eslint `vue/no-required-prop-with-default` 会把「required + default」判为
// 冗余（CI 用 --max-warnings 0，warning 也算红）。
const props = defineProps<{
  /** 当月逐日序列（父组件已按日期建 Map） */
  days: PnlCalendarDay[];
  /** 展示用月份标签，如 "2026 年 9 月" */
  monthLabel: string;
  /** 区间盈亏合计（元），仅用于 aria 描述 */
  monthTotal: number;
}>();

/** 四态的紧凑标签（与日历图格内保持同一套措辞） */
const STATE_TAG: Record<PnlCalendarState, string> = {
  updown: "",
  zero: "0.00",
  no_price: "无价",
  closed: "休市"
};

/** 当日文案：与日历图 aria 口径保持一致 */
function titleFor(
  date: string,
  state: PnlCalendarState,
  pnl: number | null
): string {
  if (state === "no_price") return `${date}：无价格序列，不参与收益计算`;
  if (state === "closed") return `${date}：非交易日或数据未同步`;
  if (state === "zero") return `${date}：收益 0.00 元`;
  return `${date}：收益 ${pnl ?? 0} 元`;
}

interface BarItem {
  key: string;
  day: number;
  title: string;
  style: Record<string, string>;
}

const bars = computed<BarItem[]>(() => {
  // 以实际返回的天数为准（区间可能不足整月），不假设 31 天
  let max = 0;
  for (const d of props.days) {
    if (d.daily_pnl != null) max = Math.max(max, Math.abs(d.daily_pnl));
  }
  const denom = max || 1;

  return props.days.map(d => {
    const dayNum = Number(d.date.slice(8, 10));
    const state = d.state;
    const pnl = d.daily_pnl;
    // 柱高占半区（0~50%），零轴居中：正数撑上半、负数撑下半
    const height = pnl == null ? 0 : Math.min(Math.abs(pnl) / denom, 1) * 50;
    const color =
      pnl == null || pnl === 0
        ? "var(--border-subtle)"
        : pnl > 0
          ? "var(--color-rise)"
          : "var(--color-fall)";
    return {
      key: d.date,
      day: dayNum,
      title: titleFor(d.date, state, pnl),
      style: {
        height: `${height}%`,
        backgroundColor: color,
        // 无数据/休市不占半区，避免被误读成"幅度极小"
        marginTop: pnl != null && pnl < 0 ? "50%" : "auto",
        marginBottom: pnl != null && pnl > 0 ? "50%" : "auto"
      }
    };
  });
});

const ariaLabel = computed(
  () => `${props.monthLabel}逐日收益柱状图，合计 ${props.monthTotal} 元`
);
</script>

<style lang="scss" scoped>
.pnl-calendar-bars {
  display: flex;
  align-items: stretch;
  gap: 2px;
  height: 160px;
  padding-top: 4px;
}

.pnl-calendar-bars__slot {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.pnl-calendar-bars__track {
  flex: 1;
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.pnl-calendar-bars__bar {
  width: 100%;
  border-radius: 2px;
  /* 有数据但幅度极小时也要留一根可见的线，否则与"无数据"不可辨 */
  min-height: 2px;
  transition: height 0.2s ease;
}

.pnl-calendar-bars__label {
  font-size: 9px;
  color: var(--text-tertiary-ink);
  line-height: 1;
}
</style>
