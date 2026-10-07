<!--
  PnlCalendarGrid · 收益日历的「日历图」视图（#1812，#1925 从 PnlCalendar 拆出）

  拆分理由与 `PnlCalendarBars` 同源：日历图与柱状图是两种呈现角度，且父组件
  长期超 `check_vue_size.mjs` 的 400 行软阈值——#1925 又要在父组件里加
  日 / 月 / 年粒度编排，先把日历图的模板、格子整形与四态配色整体搬出来。

  **只服务日粒度**：月 / 年视图是柱状图（一根柱 = 一月 / 一年），没有「日」的概念。

  四态视觉（**缺数据绝不能画成 0**，这是本组件存在的核心理由之一）：
    updown   涨红跌绿柔和填充，色深 ∝ |收益|
    zero     灰底 + 0.00（真实为零）
    no_price 斜线纹理（balance 模式无历史价格序列，如银行理财/投顾/实物）
    closed   空白（非交易日/未同步/区间首日）

  色彩纪律（design.md 硬约束）：
    - 只走 --color-rise / --color-fall（**绿跌**，不用参考图的蓝跌）；
    - 禁硬编码色值，全部 CSS 变量，var() 引用的令牌必须真实存在（check_css_vars.mjs 守卫）；
    - 柔和填充而非饱和实心块，避免长时间浏览疲劳。
-->

<template>
  <div class="pnl-calendar__grid-wrap">
    <div class="pnl-calendar__weekdays" aria-hidden="true">
      <span v-for="w in WEEKDAYS" :key="w">{{ w }}</span>
    </div>
    <div class="pnl-calendar__grid" role="grid">
      <div
        v-for="cell in calendarCells"
        :key="cell.key"
        class="pnl-calendar__cell"
        :class="[
          `is-${cell.state}`,
          {
            'is-today': cell.isToday,
            'is-void': cell.void,
            // 色深档位：仅加在有真实盈亏的格子上，零收益/无价/休市不参与映射
            [`lv-${cell.level}`]: cell.state === 'updown',
            'is-fall': cell.isFall
          }
        ]"
        role="gridcell"
        :aria-label="cell.ariaLabel"
      >
        <template v-if="!cell.void">
          <span class="pnl-calendar__day">{{ cell.day }}</span>
          <MoneyDisplay
            v-if="cell.state === 'updown' || cell.state === 'zero'"
            :value="cell.pnl"
            size="xs"
            :show-currency="false"
            :auto-color="false"
            :custom-color="cell.textColor"
          />
          <span v-else class="pnl-calendar__tag">{{
            STATE_TAG[cell.state]
          }}</span>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import type { PnlCalendarDay, PnlCalendarState } from "@/api/summary";
import { ymd } from "./helpers";

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

/** 四态的紧凑标签（格内空间有限，tooltip 里有完整解释） */
const STATE_TAG: Record<PnlCalendarState, string> = {
  updown: "",
  zero: "0.00",
  // 用户明确要求：不要说「无历史价格序列」——那是实现语言，用户看不懂，
  // 且会被误解成「我的理财出问题了」。产品语言是「暂无每日估值」。
  no_price: "暂无估值",
  closed: "休市",
  // #1917：部分断档。数值照常显示，只是可信度低——用「※」标记，
  // 用户扫一眼就知道「这天有东西没更新到」，aria/tooltip 有完整说明。
  partial: "※"
};

const dayMap = computed(() => {
  const map = new Map<string, PnlCalendarDay>();
  for (const d of props.days) map.set(d.date, d);
  return map;
});

/** 当月最大绝对盈亏，用于色深映射（避免除零） */
const maxAbsPnl = computed(() => {
  let max = 0;
  for (const d of props.days) {
    if (d.daily_pnl != null) max = Math.max(max, Math.abs(d.daily_pnl));
  }
  return max;
});

/** 色深档位：0（浅）/ 1（中）/ 2（深），由 |收益| / 月内最大值 决定 */
function intensity(pnl: number | null): 0 | 1 | 2 {
  if (pnl == null || maxAbsPnl.value === 0) return 0;
  const ratio = Math.abs(pnl) / maxAbsPnl.value;
  if (ratio >= 0.6) return 2;
  if (ratio >= 0.25) return 1;
  return 0;
}

interface CalendarCell {
  key: string;
  void: boolean;
  day: number;
  date: string;
  state: PnlCalendarState;
  pnl: number | null;
  isToday: boolean;
  isFall: boolean;
  /** 色深档位 0/1/2，由 |收益| / 月内最大绝对值 决定 */
  level: 0 | 1 | 2;
  textColor: string;
  ariaLabel: string;
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
      void: true,
      day: 0,
      date: "",
      state: "closed",
      pnl: null,
      isToday: false,
      isFall: false,
      level: 0,
      textColor: "",
      ariaLabel: ""
    });
  }

  for (let d = 1; d <= totalDays; d += 1) {
    const date = ymd(new Date(year, month, d));
    const day = dayMap.value.get(date);
    const state: PnlCalendarState = day?.state ?? "closed";
    const pnl = day?.daily_pnl ?? null;
    cells.push({
      key: date,
      void: false,
      day: d,
      date,
      state,
      pnl,
      isToday: date === todayStr,
      isFall: pnl != null && pnl < 0,
      level: intensity(pnl),
      textColor: textColorFor(state, pnl),
      ariaLabel: ariaFor(date, state, pnl)
    });
  }
  return cells;
});

/** 文字色用 -ink 级（AA 达标），底色用柔和填充 —— 二者分工见 design.md 涨跌色应用 */
function textColorFor(state: PnlCalendarState, pnl: number | null): string {
  // partial 与 updown 同用 -ink 级文字（AA 达标）：涨跌方向必须可读，
  // 区别靠底色 + 「※」承载，不能靠降级文字色。
  if ((state === "updown" || state === "partial") && pnl != null) {
    return pnl > 0 ? "var(--color-rise-ink)" : "var(--color-fall-ink)";
  }
  return "var(--text-tertiary-ink)";
}

function ariaFor(
  date: string,
  state: PnlCalendarState,
  pnl: number | null
): string {
  if (state === "no_price") return `${date}：无价格序列，不参与收益计算`;
  if (state === "closed") return `${date}：非交易日或数据未同步`;
  // #1917：数值可信但该日有标的数据不全，必须说清「不全」而非「无」
  if (state === "partial")
    return `${date}：收益 ${pnl ?? 0} 元（该日部分标的未更新估值，数据不完整）`;
  if (state === "zero") return `${date}：收益 0.00 元`;
  return `${date}：收益 ${pnl ?? 0} 元`;
}
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* 窄屏（弹窗形态）压缩格子高度，但字号有下限，保证可读 */
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

.pnl-calendar__cell {
  /* `.is-partial::after` 的斜纹叠加层需要相对定位的父元素（#1917） */
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  justify-content: center;

  /* aspect-ratio 保证格子近正方；min-height 兜底窄屏 */
  min-height: 62px;
  padding: 6px 2px;
  cursor: default;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease;
}

.pnl-calendar__day {
  font-size: 11px;
  line-height: 1;
  color: var(--text-tertiary-ink);
}

/* ── 四态视觉 ──
   updown 用柔和填充 + 涨红跌绿（**绿跌**，非参考图的蓝跌）。

   **色深上限 12% 是算出来的，不是随手填的**（实测 2026-10-06，WCAG AA 4.5:1）：
   底色 = color-mix(涨跌色, --bg-card, N%)，格内有两类文字都要达标：
     N=12% 涨：盈亏字 4.81:1 / 日期数字 4.59:1 ✅
     N=14% 涨：盈亏字 4.68:1 / 日期数字 4.47:1 ❌（日期数字跌破 AA）
   即**涨色的 12% 是硬顶**（跌色可到 24%，但两色必须同刻度，否则色深含义不一致）。
   这正是 design.md 警告的坑：日期数字走 --text-tertiary-ink（4.59:1）刚好压线，
   若图省事用 --text-tertiary（白底仅 3.69:1）则任何一档都必然不合格。
   ⇒ 色深只表达「相对大小」，**绝不允许为了视觉冲击加深到底色**。 */
.is-updown {
  border-color: var(--border-subtle);
}

.is-updown.lv-1 {
  background: color-mix(in srgb, var(--color-rise) 7%, var(--bg-card));
  border-color: color-mix(in srgb, var(--color-rise) 18%, var(--border-light));
}

.is-updown.lv-2 {
  background: color-mix(in srgb, var(--color-rise) 12%, var(--bg-card));
  border-color: color-mix(in srgb, var(--color-rise) 28%, var(--border-light));
}

.is-updown.is-fall.lv-1 {
  background: color-mix(in srgb, var(--color-fall) 7%, var(--bg-card));
  border-color: color-mix(in srgb, var(--color-fall) 18%, var(--border-light));
}

.is-updown.is-fall.lv-2 {
  background: color-mix(in srgb, var(--color-fall) 12%, var(--bg-card));
  border-color: color-mix(in srgb, var(--color-fall) 28%, var(--border-light));
}

/* 零收益：灰底 + 0.00，语义是「真的是零」 */
.is-zero {
  background: var(--bg-hover);
  border-color: var(--border-light);
}

/* 部分断档（#1917）：中性底 + 斜纹。
   ⚠️ 为什么不用涨跌底色：实测（WCAG AA，tint 12% 最深档）涨色叠斜纹后
   盈亏字 4.26 / 日期数字 4.07，双双跌破 4.5；压到 3% 仍不合格——
   涨色 tint 12% 本身已接近上限（纯底 4.81 / 日期 4.59 刚好压线），没有余量。
   「数据不全」本就与涨跌无关，中性底语义更准，对比度余量充足（3~12% 全通过）。
   涨跌方向改由 `-ink` 文字色 + 正负号承载，见 textColorFor()。

   用 `::after` 叠加层：`.pnl-calendar__cell` 用了 `background` 简写，
   会把 `background-image` 一并重置（同 specificity 下按源码顺序输赢，不可靠）。 */
.is-partial {
  background-color: var(--bg-hover);
  border-color: color-mix(
    in srgb,
    var(--text-tertiary) 30%,
    var(--border-light),
  );
}

.is-partial::after {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  content: "";
  background-image: repeating-linear-gradient(
    45deg,
    transparent,
    transparent 5px,
    color-mix(in srgb, var(--text-tertiary) 10%, transparent) 5px,
    color-mix(in srgb, var(--text-tertiary) 10%, transparent) 8px,
  );

  /* 格子有 8px 圆角，叠加层需跟着裁切，否则四角会溢出 */
  border-radius: inherit;
}

/* 文字层须在斜纹之上，否则金额与日期数字会被盖住 */
.pnl-calendar__day,
.pnl-calendar__amount {
  position: relative;
  z-index: 1;
}

/* 无价格序列：斜线纹理，与「零收益」「休市」三者可辨 */
.is-no_price {
  background: repeating-linear-gradient(
    45deg,
    transparent,
    transparent 4px,
    color-mix(in srgb, var(--text-tertiary) 12%, transparent) 4px,
    color-mix(in srgb, var(--text-tertiary) 12%, transparent) 7px
  );
  border-color: var(--border-subtle);
}

.pnl-calendar__tag {
  font-size: 10px;
  line-height: 1;
  color: var(--text-tertiary-ink);
}

/* 休市 / 首日：留白，不画任何数字（避免"看起来是 0"） */
.is-closed {
  background: transparent;
  border-color: var(--border-light);
}

/* 今日：细边框高亮，不改变底色 */
.is-today {
  outline: 2px solid var(--color-rise);
  outline-offset: -2px;
}

.is-void {
  background: transparent;
  border-color: transparent;
}

/* 响应式：窄屏压缩格子但保字号下限（design.md 可读性要求）。
   断点走 _breakpoints.scss 单一来源（`bp.below("sm")` = < 640px），
   禁手写像素——guard_breakpoints.py 会拦。 */
@include bp.below("sm") {
  .pnl-calendar__cell {
    min-height: 52px;
    padding: 4px 1px;
  }

  .pnl-calendar__day {
    font-size: 10px;
  }
}
</style>
