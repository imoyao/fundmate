<!--
  PnlCalendarBars · 收益日历的「柱状图」视图（#1812，#1925 泛化为三粒度共用）

  从 PnlCalendar 拆出（父组件长期超 `check_vue_size.mjs` 的 400 行软阈值）。
  拆分理由不是「凑行数」：柱状图与日历图是**两种呈现角度**，
  日历回答「哪几天」，柱状回答「区间起伏」，各自的数据整形逻辑也不同。

  #1925 起同一份柱状几何被日 / 月 / 年三粒度复用，只是「一根柱」的含义变了：
    day    一根柱 = 一天（月内逐日）
    month  一根柱 = 一个月（年内逐月）
    year   一根柱 = 一年（窗口内逐年）
  故 props 为归一化输入（`days` 或 `periods`，后端保证二者只有一侧非空），
  柱标签由数据自身推导——**不新建第二个柱状组件**（AGENTS.md 强制复用清单）。

  #1942 修几何（用户原话：「现在的柱状图很怪异，不符合预期」）：
  旧实现用 `margin-top / margin-bottom: 50%` 把零轴居中，而 **CSS 的垂直百分比外边距
  是按包含块的「宽度」解析的**（不是高度）。于是柱子的偏移量随容器宽度变化：
  日视图在宽卡片里每根柱被顶出 20+px、年视图只有 3 根柱时更是被顶出一个屏高，
  整排柱子飞出绘图区——这不是「审美问题」，是几何算错了。
  现在改为**绝对定位 + top/bottom 百分比**（top/bottom 的百分比按高度解析），
  并补一条真实的零轴线；柱宽加 `max-width` 上限，避免「只有 2–3 根柱」时
  被拉成占满全宽的色块（与 `PnlCalendarPeriodGrid` 的格子同一个约束）。
-->

<template>
  <div class="pnl-calendar-bars" role="img" :aria-label="ariaLabel">
    <div class="pnl-calendar-bars__plot">
      <!-- 零轴：没有它，正负柱分居上下两半却看不出「零在哪」 -->
      <span class="pnl-calendar-bars__axis" aria-hidden="true" />
      <div class="pnl-calendar-bars__slots">
        <div
          v-for="bar in bars"
          :key="bar.key"
          class="pnl-calendar-bars__slot"
          :title="bar.title"
        >
          <span
            v-if="bar.hasBar"
            class="pnl-calendar-bars__bar"
            :style="bar.style"
          />
        </div>
      </div>
    </div>
    <div class="pnl-calendar-bars__labels" aria-hidden="true">
      <span
        v-for="bar in bars"
        :key="bar.key"
        class="pnl-calendar-bars__label"
        >{{ bar.label }}</span
      >
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type {
  PnlCalendarDay,
  PnlCalendarPeriod,
  PnlCalendarState
} from "@/api/summary";
import { maxAbsPnl, stateDescription, valueIn, type PnlCalendarValueMode } from "./helpers";

defineOptions({ name: "PnlCalendarBars" });

// 四个 prop 都由父组件必传（`days` / `periods` 二选一传空数组），故不给
// withDefaults 默认值——eslint `vue/no-required-prop-with-default` 会把
// 「required + default」判为冗余（CI 用 --max-warnings 0，warning 也算红）。
const props = withDefaults(
  defineProps<{
    /** 日粒度：当月逐日序列（月 / 年粒度下后端回空数组） */
    days?: PnlCalendarDay[];
    /** 月 / 年粒度：期间聚合序列（日粒度下后端回空数组） */
    periods?: PnlCalendarPeriod[];
    /** 展示用区间标签，如 "2026 年 9 月" / "2026 年" / "2024–2026 年" */
    rangeLabel: string;
    /** 区间盈亏合计（元），仅用于 aria 描述 */
    total: number;
    /** 区间收益率（%），仅用于 aria 描述；`null` = 不可算 */
    rangeRate?: number | null;
    /** 数字口径（#1942 ②）：柱高与 aria 都按它取数 */
    mode?: PnlCalendarValueMode;
  }>(),
  { rangeRate: null, mode: "amount" }
);

interface Normalized {
  key: string;
  /** 柱下标：日粒度取「几号」，月粒度取「几月」，年粒度取年份 */
  label: string;
  name: string;
  state: PnlCalendarState;
  pnl: number | null;
  rate: number | null;
}

/** 把两种输入整形为同一份柱序列（后端保证 `days` / `periods` 只有一侧非空） */
const items = computed<Normalized[]>(() => {
  if (props.periods?.length) {
    return props.periods.map(p => ({
      key: p.period,
      // 键长即粒度：`2026-09` → 9（月），`2026` → 2026（年）
      label:
        p.period.length === 7 ? String(Number(p.period.slice(5))) : p.period,
      name: p.period,
      state: p.state,
      pnl: p.pnl,
      rate: p.rate
    }));
  }
  return (props.days ?? []).map(d => ({
    key: d.date,
    label: String(Number(d.date.slice(8, 10))),
    name: d.date,
    state: d.state,
    pnl: d.daily_pnl,
    rate: d.rate
  }));
});

interface BarItem {
  key: string;
  label: string;
  title: string;
  /** 有真实数值才画柱；`null`（未同步 / 休市 / 无持仓）整根不画 */
  hasBar: boolean;
  style: Record<string, string>;
}

const bars = computed<BarItem[]>(() => {
  // 分母按**当前口径**取数：金额与收益率的量纲不同，不能共用一套高度映射
  const denom =
    maxAbsPnl(items.value.map(it => valueIn(props.mode, it.pnl, it.rate))) ||
    1;

  return items.value.map(it => {
    // 柱高占半区（0~50%），零轴居中：正数向上撑、负数向下撑。
    // `height` / `top` / `bottom` 的百分比都按**绘图区高度**解析，
    // 不会像垂直 margin 那样按宽度算（#1942 的根因）。
    const value = valueIn(props.mode, it.pnl, it.rate);
    const height = value == null ? 0 : Math.min(Math.abs(value) / denom, 1) * 50;
    const style: Record<string, string> = {};
    if (value == null) {
      // 无数据：不画。画一根 0 高度的灰线会被读成「幅度极小」，正是「缺数据
      // 不能画成 0」的反面（日历图用空白格表达同一件事）。
      //
      // 收益率口径下还有第二种 `null`：有金额但没有「前一日基准」⇒ 收益率不可算。
      // 同样不画——把不可算画成零轴短横会与「真实为零」混淆。
    } else if (value > 0) {
      style.height = `${height}%`;
      style.bottom = "50%";
      style.backgroundColor = "var(--color-rise)";
    } else if (value < 0) {
      style.height = `${height}%`;
      style.top = "50%";
      style.backgroundColor = "var(--color-fall)";
    } else {
      // 真实为零：在零轴上画一道短横，与「无数据」可辨
      style.height = "2px";
      style.top = "calc(50% - 1px)";
      style.backgroundColor = "var(--border-default)";
    }
    return {
      key: it.key,
      label: it.label,
      title: stateDescription(it.name, it.state, it.pnl),
      hasBar: value != null,
      style
    };
  });
});

const ariaLabel = computed(() => {
  const unit = props.periods?.length ? "期间" : "逐日";
  // 合计也随口径说话：切换后读屏拿到的单位必须与屏幕上的数字一致
  const totalText =
    props.mode === "rate"
      ? props.rangeRate == null
        ? "区间收益率不可算"
        : `合计 ${props.rangeRate}%`
      : `合计 ${props.total} 元`;
  return `${props.rangeLabel}${unit}收益柱状图，${totalText}`;
});
</script>

<style lang="scss" scoped>
.pnl-calendar-bars {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pnl-calendar-bars__plot {
  position: relative;
  height: 160px;
}

/* 零轴：贯穿整幅绘图区的一条细线（柱子贴着它上下生长） */
.pnl-calendar-bars__axis {
  position: absolute;
  inset-inline: 0;
  top: 50%;
  height: 1px;
  background: var(--border-light);
}

.pnl-calendar-bars__slots {
  position: relative;
  display: flex;
  gap: 2px;
  align-items: stretch;
  height: 100%;
}

.pnl-calendar-bars__slot {
  position: relative;
  flex: 1;
  min-width: 0;
}

.pnl-calendar-bars__bar {
  position: absolute;
  left: 50%;
  width: 100%;

  /* 上限：只有 2–3 根柱时不被拉成占满全宽的色块（与方格图同一个约束） */
  max-width: 24px;
  min-height: 2px;
  border-radius: 2px;
  transform: translateX(-50%);
  transition: height 0.2s ease;
}

/* 标签行与柱槽同构（同样的 flex 与 gap），故天然对齐 */
.pnl-calendar-bars__labels {
  display: flex;
  gap: 2px;
}

.pnl-calendar-bars__label {
  flex: 1;
  min-width: 0;
  font-size: 9px;
  line-height: 1;
  color: var(--text-tertiary-ink);
  text-align: center;
}
</style>
