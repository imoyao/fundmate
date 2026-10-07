<!--
  PnlCalendarBars · 收益日历的「柱状图」视图（#1812，#1925 泛化为三粒度共用）

  从 PnlCalendar 拆出（父组件长期超 `check_vue_size.mjs` 的 400 行软阈值）。
  拆分理由不是「凑行数」：柱状图与日历图是**两种呈现角度**，
  日历回答「哪几天」，柱状回答「区间起伏」，各自的数据整形逻辑也不同
  （柱状要算零轴上下半区的高度百分比，日历要算色深档位）。

  #1925 起同一份柱状几何被日 / 月 / 年三粒度复用，只是「一根柱」的含义变了：
    day    一根柱 = 一天（月内逐日）
    month  一根柱 = 一个月（年内逐月）
    year   一根柱 = 一年（窗口内逐年）
  故 props 改为归一化输入（`days` 或 `periods`，后端保证二者只有一侧非空），
  柱标签由数据自身推导——**不新建第二个柱状组件**（AGENTS.md 强制复用清单）。
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
      <span class="pnl-calendar-bars__label">{{ bar.label }}</span>
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

defineOptions({ name: "PnlCalendarBars" });

// 四个 prop 都由父组件必传（`days` / `periods` 二选一传空数组），故不给
// withDefaults 默认值——eslint `vue/no-required-prop-with-default` 会把
// 「required + default」判为冗余（CI 用 --max-warnings 0，warning 也算红）。
const props = defineProps<{
  /** 日粒度：当月逐日序列（月 / 年粒度下后端回空数组） */
  days?: PnlCalendarDay[];
  /** 月 / 年粒度：期间聚合序列（日粒度下后端回空数组） */
  periods?: PnlCalendarPeriod[];
  /** 展示用区间标签，如 "2026 年 9 月" / "2026 年" / "2024–2026 年" */
  rangeLabel: string;
  /** 区间盈亏合计（元），仅用于 aria 描述 */
  total: number;
}>();

/** 单根柱的文案：`name` 是日期 ISO 或期间键，与日历图 aria 口径保持一致 */
function titleFor(
  name: string,
  state: PnlCalendarState,
  pnl: number | null
): string {
  if (state === "no_price") return `${name}：无价格序列，不参与收益计算`;
  if (state === "closed") return `${name}：非交易日或数据未同步`;
  if (state === "zero") return `${name}：收益 0.00 元`;
  return `${name}：收益 ${pnl ?? 0} 元`;
}

interface Normalized {
  key: string;
  /** 柱下标：日粒度取「几号」，月粒度取「几月」，年粒度取年份 */
  label: string;
  name: string;
  state: PnlCalendarState;
  pnl: number | null;
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
      pnl: p.pnl
    }));
  }
  return (props.days ?? []).map(d => ({
    key: d.date,
    label: String(Number(d.date.slice(8, 10))),
    name: d.date,
    state: d.state,
    pnl: d.daily_pnl
  }));
});

interface BarItem {
  key: string;
  label: string;
  title: string;
  style: Record<string, string>;
}

const bars = computed<BarItem[]>(() => {
  // 以实际返回的柱数为准（区间可能不足整月 / 整年），不假设 31 或 12
  let max = 0;
  for (const it of items.value) {
    if (it.pnl != null) max = Math.max(max, Math.abs(it.pnl));
  }
  const denom = max || 1;

  return items.value.map(it => {
    // 柱高占半区（0~50%），零轴居中：正数撑上半、负数撑下半
    const height =
      it.pnl == null ? 0 : Math.min(Math.abs(it.pnl) / denom, 1) * 50;
    const color =
      it.pnl == null || it.pnl === 0
        ? "var(--border-subtle)"
        : it.pnl > 0
          ? "var(--color-rise)"
          : "var(--color-fall)";
    return {
      key: it.key,
      label: it.label,
      title: titleFor(it.name, it.state, it.pnl),
      style: {
        height: `${height}%`,
        backgroundColor: color,
        // 无数据/休市不占半区，避免被误读成"幅度极小"
        marginTop: it.pnl != null && it.pnl < 0 ? "50%" : "auto",
        marginBottom: it.pnl != null && it.pnl > 0 ? "50%" : "auto"
      }
    };
  });
});

const ariaLabel = computed(() => {
  const unit = props.periods?.length ? "期间" : "逐日";
  return `${props.rangeLabel}${unit}收益柱状图，合计 ${props.total} 元`;
});
</script>

<style lang="scss" scoped>
.pnl-calendar-bars {
  display: flex;
  gap: 2px;
  align-items: stretch;
  height: 160px;
  padding-top: 4px;
}

.pnl-calendar-bars__slot {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  min-width: 0;
}

.pnl-calendar-bars__track {
  display: flex;
  flex: 1;
  flex-direction: column;
  justify-content: center;
  width: 100%;
}

.pnl-calendar-bars__bar {
  width: 100%;

  /* 有数据但幅度极小时也要留一根可见的线，否则与"无数据"不可辨 */
  min-height: 2px;
  border-radius: 2px;
  transition: height 0.2s ease;
}

.pnl-calendar-bars__label {
  font-size: 9px;
  line-height: 1;
  color: var(--text-tertiary-ink);
}
</style>
