<!--
  PnlCalendarGrid · 收益日历的「日历图」（日粒度，#1812；#1925 从 PnlCalendar 拆出）

  **只服务日粒度**：月 / 年视图没有「日」的概念，走 `PnlCalendarPeriodGrid`
  的方格图（一根柱 = 一月 / 一年的柱状图见 `PnlCalendarBars`）。

  本组件只负责**日历排版**（周一为第一列、首行补空格、列数见下）与把逐日序列
  摊成格子；格子的七态配色、文案与色深档位全部住在 `PnlCalendarTile.vue`
  ——#1942 扩状态时不再改这里，避免三套格子各写一份配色。

  **默认 5 列（一~五），周末不占格**（#1942 第二轮反馈：*「盈亏日历似乎没有必要
  列出周末，周末对我们的数据永远都是空的，这种空 UI 设计有什么价值」*）。
  A 股交易日只可能落在工作日，周末格既不可点、也无数据、也不承担对齐职责——
  信息量为 0，却让月份面积膨胀约三分之一、把有数的格子挤窄。周末那两列去掉后，
  30 天的月份从「7×5 格 + 8 个空位」变成 22 格，每格还能宽出约 40%。

  **但「周末永远无数据」是假设，不是事实**——故给了数据驱动的兜底：
  只要该月存在任何一个周末日**不是** `closed`（真有估值/收益），自动切回 7 列，
  否则将来口径变化（例如新增周末交易的品种）会被这里静默吞掉。判据用后端
  下发的 `state`，不在这里二次判断交易日。
-->

<template>
  <div class="pnl-calendar__grid-wrap">
    <div
      class="pnl-calendar__weekdays"
      :class="`is-cols-${visibleColumns.length}`"
      aria-hidden="true"
    >
      <span v-for="w in weekdayLabels" :key="w">{{ w }}</span>
    </div>
    <div
      class="pnl-calendar__grid"
      :class="`is-cols-${visibleColumns.length}`"
      role="grid"
    >
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
import {
  intensity,
  maxAbsPnl,
  stateDescription,
  weekdayLabel,
  weekdayOf,
  ymd
} from "./helpers";

defineOptions({ name: "PnlCalendarGrid" });

const props = defineProps<{
  /** 逐日序列（父组件保证仅日粒度下渲染本组件） */
  days: PnlCalendarDay[];
  /** 展示年份 */
  year: number;
  /** 月份下标（0 = 1 月，与 `Date.getMonth()` 一致） */
  monthIndex: number;
}>();

/** 周一~周五：默认列集（周末不占格，见文件头） */
const WEEKDAY_COLUMNS = [1, 2, 3, 4, 5] as const;
/** 兜底列集：周末确有数据时才用（含周六、周日，周一为第一列） */
const FULL_WEEK_COLUMNS = [1, 2, 3, 4, 5, 6, 0] as const;

const dayMap = computed(() => {
  const map = new Map<string, PnlCalendarDay>();
  for (const d of props.days) map.set(d.date, d);
  return map;
});

/** 当月最大绝对盈亏，用于色深映射（避免除零） */
const maxAbs = computed(() => maxAbsPnl(props.days.map(d => d.daily_pnl)));

/**
 * 该月是否存在「周末却有数据」的日子。
 *
 * 判据用后端下发的 `state`（`closed` 的判据是 A 股开盘日历，见 `services/pnl_calendar`），
 * 不在前端二次判断交易日；`days` 只覆盖请求区间，而请求区间就是这个月，
 * 故遍历 `days` 即可（不需要再算一遍月份天数）。
 */
const hasWeekendData = computed(() =>
  props.days.some(d => {
    const wd = weekdayOf(d.date);
    return (wd === 0 || wd === 6) && d.state !== "closed";
  })
);

/** 本次渲染的可见列（`Date.getDay()` 值序：周一为第一列） */
const visibleColumns = computed<readonly number[]>(() =>
  hasWeekendData.value ? FULL_WEEK_COLUMNS : WEEKDAY_COLUMNS
);

const weekdayLabels = computed(() => visibleColumns.value.map(weekdayLabel));

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
  const cols = visibleColumns.value;
  const totalDays = new Date(year, month + 1, 0).getDate();
  const todayStr = ymd(new Date());

  /*
   * 首行补空格 = 1 号所在列的序号。
   *
   * 1 号本身是周末时该列不存在（`indexOf` 回 -1）⇒ 补 0 格，第一个有格的日期
   * 自然落在第一列：那是**本月第一个可见工作日**（周末已整体不排），对齐依然正确。
   * 这里刻意不保留整行空位——「周末不占格」也包括不留一整行空白。
   */
  const firstWeekdayIdx = cols.indexOf(new Date(year, month, 1).getDay());
  const leading = firstWeekdayIdx >= 0 ? firstWeekdayIdx : 0;

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
    // 不可见列（默认是周末）整格不排：不占位、不进 tab 序
    if (!cols.includes(weekdayOf(date))) continue;
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
  gap: 6px;

  span {
    font-size: 11px;
    color: var(--text-tertiary-ink);
    text-align: center;
  }
}

.pnl-calendar__grid {
  display: grid;
  gap: 6px;
}

/* 列数只有两种（5 = 工作日 / 7 = 含周末兜底，见文件头）。写死两条而不是
   用 CSS 变量拼 `repeat(var(--n), …)`：`--n` 属组件内局部自定义属性，
   check_css_vars.mjs 只认全局令牌表，会把它判成未定义令牌。 */
.pnl-calendar__weekdays.is-cols-5,
.pnl-calendar__grid.is-cols-5 {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.pnl-calendar__weekdays.is-cols-7,
.pnl-calendar__grid.is-cols-7 {
  grid-template-columns: repeat(7, minmax(0, 1fr));
}
</style>
