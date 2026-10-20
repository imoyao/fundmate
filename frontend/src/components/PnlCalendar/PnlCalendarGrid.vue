<!--
  PnlCalendarGrid · 收益日历的「日历图」（日粒度，#1812；#1925 从 PnlCalendar 拆出）

  **只服务日粒度**：月 / 年视图没有「日」的概念，走 `PnlCalendarPeriodGrid`
  的方格图（一根柱 = 一月 / 一年的柱状图见 `PnlCalendarBars`）。

  本组件只负责**日历排版**（周一为第一列、首行补空格）与把逐日序列摊成格子；
  格子的七态配色、文案与色深档位全部住在 `PnlCalendarTile.vue`
  ——#1942 扩状态时不再改这里，避免三套格子各写一份配色。

  **固定 5 列（一~五），周末永不占格**（2026-10-17 用户拍板「周六、周日固定休市」）：
  A 股交易日历（`core/trading_calendar.is_trading_day`，后端唯一权威）下周末恒为
  `closed`，日历图不再给周末留列。30 天的月份从「7×5 格 + 8 个空位」变成 22 格，
  每格宽出约 40%。

  ── 为什么删掉了「周末有数据就切 7 列」的兜底（#1942 旧逻辑，2026-10-17 作废）──
  旧兜底为「周末永远无数据只是假设」而设：任一周末日 `state != closed` 即切回
  7 列。它把判材押在后端逐日状态上，而周末的 `state` 会被两类与 A 股开盘无关的
  数据形态污染：
    · 未来周末日前值回填窗耗尽，被判 `no_price`（真实库 2026-10-17 实测 10/24、
      10/25、10/31）⇒ 用户看到「定好的固定休市没生效，10 月又排出周末」；
    · 遇周末发布估值的标的（货基），周末被判 `partial`。
  现在后端状态链把交易日判定前移到最顶（pnl_calendar.py #2277），周末恒
  `closed`；前端同步删兜底——两边都按「周六、周日固定休市」这一条口径办事，
  不再让数据 quirk 有机会把两列周末排回日历。周末真发生估值变动（货基）由
  后端的水平值消化：当日不出数，收益并入下一开盘日的差分。
-->

<template>
  <div class="pnl-calendar__grid-wrap">
    <div
      class="pnl-calendar__weekdays"
      :class="`is-cols-${VISIBLE_COLUMNS.length}`"
      aria-hidden="true"
    >
      <span v-for="w in weekdayLabels" :key="w">{{ w }}</span>
    </div>
    <div
      class="pnl-calendar__grid"
      :class="`is-cols-${VISIBLE_COLUMNS.length}`"
      role="grid"
    >
      <template v-for="cell in calendarCells" :key="cell.key">
        <PnlCalendarTile
          v-if="cell.voidCell"
          label=""
          state="closed"
          :pnl="null"
          :level="0"
          void-cell
        />
        <!-- 悬浮卡片取代原先的浏览器原生 `title`（#1942 ③）：原生提示延迟约 1 秒、
             样式不可控、窄屏直接截断，且塞不下结构。卡片内容与读屏文案同源
             （`stateDescription` / `PnlCalendarUnitTip`），不会两处说法不一致。 -->
        <el-tooltip
          v-else
          placement="top"
          :show-after="120"
          :hide-after="0"
          popper-class="rich-tip"
        >
          <PnlCalendarTile
            role="gridcell"
            :label="cell.label"
            :state="cell.state"
            :pnl="cell.pnl"
            :rate="cell.rate"
            :mode="mode"
            :level="cell.level"
            :is-today="cell.isToday"
            :estimated="cell.estimated"
            :aria-label="cell.title"
          />
          <template #content>
            <PnlCalendarUnitTip
              :name="cell.key"
              :state="cell.state"
              :pnl="cell.pnl"
              :rate="cell.rate"
              :estimated="cell.estimated"
            />
          </template>
        </el-tooltip>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { PnlCalendarDay, PnlCalendarState } from "@/api/summary";
import PnlCalendarTile from "./PnlCalendarTile.vue";
import PnlCalendarUnitTip from "./PnlCalendarUnitTip.vue";
import {
  intensity,
  maxAbsPnl,
  stateDescription,
  valueIn,
  weekdayLabel,
  weekdayOf,
  ymd,
  type PnlCalendarValueMode
} from "./helpers";

defineOptions({ name: "PnlCalendarGrid" });

const props = withDefaults(
  defineProps<{
    /** 逐日序列（父组件保证仅日粒度下渲染本组件） */
    days: PnlCalendarDay[];
    /** 展示年份 */
    year: number;
    /** 月份下标（0 = 1 月，与 `Date.getMonth()` 一致） */
    monthIndex: number;
    /** 数字口径（#1942 ②）：金额 / 收益率。色深也按同一口径算，换口径要重算档位 */
    mode?: PnlCalendarValueMode;
  }>(),
  { mode: "amount" }
);

/**
 * 周一~周五：唯一列集（周六、周日固定休市，周末永不占格，见文件头）。
 *
 * #1942 曾按「该月有无周末数据」在 5 / 7 列之间切换，2026-10-17 作废：
 * 周末 `state` 会被未来日回填耗尽（`no_price`）/ 货基周末估值（`partial`）
 * 污染，兜底因此把 10 月的周六周日又排回日历；后端已保证周末恒 `closed`，
 * 前端无需再按数据猜。
 */
const VISIBLE_COLUMNS = [1, 2, 3, 4, 5] as const;

const dayMap = computed(() => {
  const map = new Map<string, PnlCalendarDay>();
  for (const d of props.days) map.set(d.date, d);
  return map;
});

/** 当月最大绝对值（按**当前口径**取数），用于色深映射（避免除零） */
const maxAbs = computed(() =>
  maxAbsPnl(props.days.map(d => valueIn(props.mode, d.daily_pnl, d.rate)))
);

const weekdayLabels = VISIBLE_COLUMNS.map(weekdayLabel);

interface CalendarCell {
  key: string;
  voidCell: boolean;
  label: string;
  state: PnlCalendarState;
  pnl: number | null;
  rate: number | null;
  isToday: boolean;
  /** 当日行按收盘估值预估（后端 `estimated` 标记，#2141）；前端不自行推断 */
  estimated: boolean;
  /** 色深档位 0/1/2，由 |当前口径数值| / 区间内最大绝对值 决定 */
  level: 0 | 1 | 2;
  /** tooltip 与 `aria-label` 共用的一份文案（不写死两处，避免读屏与悬停分叉） */
  title: string;
}

const calendarCells = computed<CalendarCell[]>(() => {
  const year = props.year;
  const month = props.monthIndex;
  const cols: readonly number[] = VISIBLE_COLUMNS;
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
      rate: null,
      isToday: false,
      estimated: false,
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
    const rate = day?.rate ?? null;
    cells.push({
      key: date,
      voidCell: false,
      label: String(d),
      state,
      pnl,
      rate,
      isToday: date === todayStr,
      // 后端 day_uses_estimate 落点（#2141）：徽标据此展示，不在前端按日期猜
      estimated: day?.estimated === true,
      // 色深按当前口径的比例算：金额大不等于收益率高，两个口径的档位必须各算各的
      level: intensity(valueIn(props.mode, pnl, rate), maxAbs.value),
      title: stateDescription(date, state, pnl)
    });
  }
  return cells;
});
</script>

<style lang="scss" scoped>
.pnl-calendar__grid-wrap {
  display: flex;

  /* #2033：宿主给了确定高度就填满，没给仍是自然高（另两处宿主逐像素不变）。 */
  flex: 1;
  flex-direction: column;
  gap: 6px;
}

.pnl-calendar__weekdays {
  display: grid;
  gap: 6px;

  span {
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
    text-align: center;
  }
}

.pnl-calendar__grid {
  display: grid;

  /* 行高交给容器分配（`1fr`）：高度不定的宿主里 1fr 按内容算，等同改动前；
     高度确定的宿主里各行等分，把可用高度用满（#2033）。压不动时由格子的
     `min-height: 62px` 兜底——**不要**为了塞进容器去改那个下限。 */
  flex: 1;
  grid-auto-rows: 1fr;
  gap: 6px;
}

/* 列数固定 5（一~五，周六、周日固定休市，见文件头）。
   写死一条，而不是把列数做成组件内的局部自定义属性再拼 repeat：局部属性不在
   全站令牌表里，`check_css_vars.mjs` 只认全站令牌，会把它判成「未定义令牌」。
   （这条注释里也不要写出该属性的 var() 写法，守卫读的是文本、不区分注释。）
   #1942 的 `is-cols-7`（周末兜底列集）已于 2026-10-17 随兜底一并删除。 */
.pnl-calendar__weekdays.is-cols-5,
.pnl-calendar__grid.is-cols-5 {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}
</style>
