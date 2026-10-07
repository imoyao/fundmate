<!--
  PnlCalendarGrid · 收益日历的「日历图」（日粒度，#1812；#1925 从 PnlCalendar 拆出）

  **只服务日粒度**：月 / 年视图没有「日」的概念，走 `PnlCalendarPeriodGrid`
  的方格图（一根柱 = 一月 / 一年的柱状图见 `PnlCalendarBars`）。

  本组件只负责**日历排版**（周一为第一列、首行补空格、7 列对齐）与把逐日序列
  摊成格子；格子的六态配色、文案与色深档位全部住在 `PnlCalendarTile.vue`
  ——#1942 扩状态时不再改这里，避免三套格子各写一份配色。
-->

<template>
  <div class="pnl-calendar__grid-wrap">
    <div class="pnl-calendar__weekdays" aria-hidden="true">
      <span v-for="w in WEEKDAYS" :key="w">{{ w }}</span>
    </div>
    <div class="pnl-calendar__grid" role="grid">
      <PnlCalendarTile
        v-for="cell in calendarCells"
        :key="cell.key"
        :role="cell.voidCell ? undefined : 'gridcell'"
        :label="cell.label"
        :state="cell.state"
        :pnl="cell.pnl"
        :level="cell.level"
        :void-cell="cell.voidCell"
        :is-today="cell.isToday"
        :title="cell.voidCell ? undefined : cell.title"
        :aria-label="cell.voidCell ? undefined : cell.title"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { PnlCalendarDay, PnlCalendarState } from "@/api/summary";
import PnlCalendarTile from "./PnlCalendarTile.vue";
import { intensity, maxAbsPnl, stateDescription, ymd } from "./helpers";

defineOptions({ name: "PnlCalendarGrid" });

const props = defineProps<{
  /** 逐日序列（父组件保证仅日粒度下渲染本组件） */
  days: PnlCalendarDay[];
  /** 展示年份 */
  year: number;
  /** 月份下标（0 = 1 月，与 `Date.getMonth()` 一致） */
  monthIndex: number;
}>();

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"] as const;

const dayMap = computed(() => {
  const map = new Map<string, PnlCalendarDay>();
  for (const d of props.days) map.set(d.date, d);
  return map;
});

/** 当月最大绝对盈亏，用于色深映射（避免除零） */
const maxAbs = computed(() => maxAbsPnl(props.days.map(d => d.daily_pnl)));

interface CalendarCell {
  key: string;
  voidCell: boolean;
  label: string;
  state: PnlCalendarState;
  pnl: number | null;
  isToday: boolean;
  /** 色深档位 0/1/2，由 |收益| / 月内最大绝对值 决定 */
  level: 0 | 1 | 2;
  /** tooltip 与 `aria-label` 共用的一份文案（不写死两处，避免读屏与悬停分叉） */
  title: string;
}

const calendarCells = computed<CalendarCell[]>(() => {
  const year = props.year;
  const month = props.monthIndex;
  const first = new Date(year, month, 1);
  // getDay(): 0=周日 → 转为周一为 0 的偏移
  const leading = (first.getDay() + 6) % 7;
  const totalDays = new Date(year, month + 1, 0).getDate();
  const todayStr = ymd(new Date());

  const cells: CalendarCell[] = [];
  for (let i = 0; i < leading; i += 1) {
    cells.push({
      key: `void-${i}`,
      voidCell: true,
      label: "",
      state: "closed",
      pnl: null,
      isToday: false,
      level: 0,
      title: ""
    });
  }

  for (let d = 1; d <= totalDays; d += 1) {
    const date = ymd(new Date(year, month, d));
    const day = dayMap.value.get(date);
    // 区间内没有这一天（例如后端区间边界）按休市处理：不画数字，也不说「0 收益」
    const state: PnlCalendarState = day?.state ?? "closed";
    const pnl = day?.daily_pnl ?? null;
    cells.push({
      key: date,
      voidCell: false,
      label: String(d),
      state,
      pnl,
      isToday: date === todayStr,
      level: intensity(pnl, maxAbs.value),
      title: stateDescription(date, state, pnl)
    });
  }
  return cells;
});
</script>

<style lang="scss" scoped>
.pnl-calendar__grid-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pnl-calendar__weekdays {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;

  span {
    font-size: 11px;
    color: var(--text-tertiary-ink);
    text-align: center;
  }
}

.pnl-calendar__grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
}
</style>
