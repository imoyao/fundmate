<!--
  PnlCalendarPeriodGrid · 收益日历的「方格图」（月 / 年粒度，#1942 新增）

  为什么月 / 年也要方格图：它们**原本只有柱状图**，而日视图既有日历图又有柱状图。
  用户的原话是「切换到月收益（12 个月）和年收益（投资以来每一年占一个方格）
  只有柱状图了」——他用「方格」描述的是他期望看到的形态：**一格一个期间**，
  一眼看全，而不是在一条细柱上比高低。

  与柱状图的分工（同一份数据、两个角度）：
    方格图  回答「哪些期间赚了 / 亏了 / 没数据」，逐格可读、可点击下钻
    柱状图  回答「区间起伏」，看连续趋势
  两者都直接消费后端的 `periods[]`，**前端不做任何二次盈亏计算**。

  下钻链（点击即选中）：
    年格 → 该年的月格 → 该月的日视图

  视觉实现全部委托给 `PnlCalendarTile`（六态配色与文案的唯一实现）；
  本组件只做**排版**，并把「可点击」放在 `<button>` 上而不是格子上——
  在 `<span>` 上挂 `@click` 会被 `guard_a11y_interaction.py` 拦，
  而把 `<div>` 塞进 `<button>` 是无效 HTML，故按钮只做透明点击区、格子仍是 `<span>`。
-->

<template>
  <!-- 外层只承担一件事：**在宿主给出的确定高度里安放方格网**（#2033）。
       装得下就由 `1fr` 把格子拉满，装不下（年格数量随「投资以来」逐年增长）
       就在这一层内部滚动——不让它把卡片打爆。
       `min-height: 0` 是前提：没有它，flex 项的自动最小尺寸会把内容高度顶回来，
       滚动永远不会触发。宿主高度不定时（welcome / 账户详情）这里不产生任何滚动，
       排版与改动前完全一致。 -->
  <div class="pnl-calendar-period-grid-wrap">
    <div
      class="pnl-calendar-period-grid"
      :class="`is-${granularity}`"
      role="group"
      :aria-label="groupLabel"
    >
      <!-- 悬浮卡片取代浏览器原生 `title`（#1942 ③）：原生提示延迟约 1 秒、样式不可控。
           触发元素仍是那个透明 `<button>`（键盘可达 + `aria-label` 在按钮上），
           el-tooltip 不渲染任何包装 DOM，故不影响这里的 grid 排版。 -->
      <el-tooltip
        v-for="tile in tiles"
        :key="tile.period"
        placement="top"
        :show-after="120"
        :hide-after="0"
        popper-class="rich-tip"
      >
        <button
          type="button"
          class="pnl-calendar-period-grid__slot"
          :aria-label="tile.title"
          @click="emit('select', tile.period)"
        >
          <PnlCalendarTile
            :label="tile.label"
            :state="tile.state"
            :pnl="tile.pnl"
            :rate="tile.rate"
            :mode="mode"
            :level="tile.level"
          />
        </button>
        <template #content>
          <PnlCalendarUnitTip
            :name="tile.period"
            :state="tile.state"
            :pnl="tile.pnl"
            :rate="tile.rate"
          />
        </template>
      </el-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { PnlCalendarPeriod, PnlCalendarState } from "@/api/summary";
import PnlCalendarTile from "./PnlCalendarTile.vue";
import PnlCalendarUnitTip from "./PnlCalendarUnitTip.vue";
import {
  intensity,
  maxAbsPnl,
  stateDescription,
  valueIn,
  type PnlCalendarValueMode
} from "./helpers";

defineOptions({ name: "PnlCalendarPeriodGrid" });

const props = withDefaults(
  defineProps<{
    /** 期间聚合序列（后端 `granularity=month|year` 的输出） */
    periods: PnlCalendarPeriod[];
    /** 期间粒度：`month` = 一格一月，`year` = 一格一年 */
    granularity: "month" | "year";
    /** 数字口径（#1942 ②）：金额 / 收益率 */
    mode?: PnlCalendarValueMode;
  }>(),
  { mode: "amount" }
);

const emit = defineEmits<{
  /** 点击某格：父组件据此下钻（年→月→日） */
  (e: "select", period: string): void;
}>();

interface Tile {
  period: string;
  label: string;
  state: PnlCalendarState;
  pnl: number | null;
  rate: number | null;
  level: 0 | 1 | 2;
  title: string;
}

/**
 * 格内小标签：键长即粒度（后端 `_period_key` 的契约）。
 *
 * 月格说「9 月」而不是「2026-09」——年份已经写在区间导航上，
 * 12 个格子重复四位数只会挤压金额的位置；年格直接说「2026」。
 */
function labelOf(period: string): string {
  return period.length === 7 ? `${Number(period.slice(5))} 月` : period;
}

const tiles = computed<Tile[]>(() => {
  const maxAbs = maxAbsPnl(
    props.periods.map(p => valueIn(props.mode, p.pnl, p.rate))
  );
  return props.periods.map(p => ({
    period: p.period,
    label: labelOf(p.period),
    state: p.state,
    pnl: p.pnl,
    rate: p.rate,
    level: intensity(valueIn(props.mode, p.pnl, p.rate), maxAbs),
    title: stateDescription(p.period, p.state, p.pnl)
  }));
});

const groupLabel = computed(() =>
  props.granularity === "year" ? "按年的收益方格" : "按月的收益方格"
);
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.pnl-calendar-period-grid-wrap {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
}

.pnl-calendar-period-grid {
  display: grid;

  /* 行高交给容器分配（`1fr`）：高度不定的宿主里按内容算（等同改动前），
     高度确定的宿主里各行等分把容器用满（#2033）。`1fr` 压不动格子的
     `min-height: 62px`，超出部分由外层滚动容器接管——这是有意为之。 */
  flex: 1;

  /* 年格数量随「投资以来」增长，用 auto-fill 自动换行；单格上限见下方 slot */
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
  grid-auto-rows: 1fr;
  gap: 6px;
}

/* 月格固定 6 列（12 个月正好 6×2），与日视图的 7 列日历同理：
   列数固定才能一眼比对同一列的不同年份 / 季度 */
.pnl-calendar-period-grid.is-month {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}

.pnl-calendar-period-grid__slot {
  /* 透明点击区：视觉盒子由 PnlCalendarTile 提供，这里只负责命中与焦点 */
  width: 100%;

  /* 上限防止「投资以来只有 2 年」时两格被拉成半个屏宽的横条（#1942 的柱状图
     也是同一个毛病：格子 / 柱子的宽度应由数量决定，不由容器决定） */
  max-width: 176px;
  padding: 0;
  margin-inline: auto;
  font: inherit;
  color: inherit;
  cursor: pointer;
  background: none;
  border: 0;

  &:hover .pnl-calendar__cell {
    box-shadow: var(--shadow-raised);
    transform: translateY(-1px);
  }

  &:focus-visible {
    outline: none;
  }

  &:focus-visible .pnl-calendar__cell {
    box-shadow: var(--focus-ring);
  }
}

/* 窄屏（半宽容器 / 移动端）：月格 3 列，年格最小宽度再收一档 */
@include bp.below("sm") {
  .pnl-calendar-period-grid {
    grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
  }

  .pnl-calendar-period-grid.is-month {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
