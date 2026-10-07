<!--
  PnlCalendarTile · 收益日历的「一个格子」（#1942 从 PnlCalendarGrid 抽出）

  三种视图共用同一个格子：日视图的「一天」、月视图的「一个月」、年视图的「一年」，
  差别只在格内小标签叫什么、以及能不能点击下钻。抽出来的理由不是「省几行」：

  · #1925 的柱状图已经拆过一次，日历图还与父组件混在一起；
  · #1942 要在四态之外补 `partial`（#1917）/ `no_data` 未同步 / `no_position` 无持仓，
    若日 / 月 / 年三套格子各写一份配色与文案，扩一次状态就要改三处，
    且必然出现「同一个状态在日历图叫未同步、在方格图叫没数据」的分叉。

  语义（谁是 gridcell、谁可点击）**不在这里**：本组件根元素是 `<span>`，
  调用方把 `role` / `aria-label` / `title` 直接写在组件标签上（属性会落到根元素），
  可点击的年 / 月格子则由调用方在外面套一个 `<button>`。这样既不用在 `<span>` 上挂
  `@click`（守卫 `guard_a11y_interaction.py` 会拦），也不会把 `<div>` 塞进 `<button>`。

  七态视觉（**缺数据绝不能画成 0**，这是本组件存在的核心理由之一）：
    updown       涨红跌绿柔和填充，色深 ∝ |收益|
    zero         灰底 + 0.00（真实为零）
    partial      中性底 + 斜纹 + 「※」（#1917：值照给，只是该日数据不完整）
    no_price     斜线纹理（balance 模式无历史价格序列，如银行理财/投顾/实物）
    no_data      虚线边框 + 「未同步」（开盘日却一个可用价都没有，#1942）
    no_position  空白 + 「无持仓」（建仓前 / 清仓后，#1942；无问题可处置，故不用虚线）
    closed       空白 + 「休市」（非 A 股开盘日）

  色彩纪律（design.md 硬约束）：
    - 只走 --color-rise / --color-fall（**绿跌**，不用参考图的蓝跌）；
    - 禁硬编码色值，全部 CSS 变量，var() 引用的令牌必须真实存在（check_css_vars.mjs 守卫）；
    - 柔和填充而非饱和实心块，避免长时间浏览疲劳。
-->

<template>
  <span
    class="pnl-calendar__cell"
    :class="[
      `is-${state}`,
      {
        'is-today': isToday,
        'is-void': voidCell,
        // 色深档位：只加在普通过涨跌格上。零收益 / partial / 无价 / 未同步 / 休市
        // 都不参与映射——partial 另有中性底 + 斜纹，叠涨跌 tint 会跌破 AA（见样式注释）。
        [`lv-${level}`]: state === 'updown',
        'is-fall': isFall
      }
    ]"
  >
    <template v-if="!voidCell">
      <span class="pnl-calendar__day">{{ label }}</span>
      <MoneyDisplay
        v-if="hasValue"
        :value="pnl"
        size="xs"
        :show-currency="false"
        :auto-color="false"
        :custom-color="textColor"
      />
      <span v-else class="pnl-calendar__tag">{{ stateTag(state) }}</span>
    </template>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import type { PnlCalendarState } from "@/api/summary";
import { stateTag } from "./helpers";

defineOptions({ name: "PnlCalendarTile" });

const props = withDefaults(
  defineProps<{
    /** 格内小标签：日视图传「几号」，月视图传「几月」，年视图传年份 */
    label: string | number;
    state: PnlCalendarState;
    /** 该单元的盈亏（元）；`null` = 不可算（缺数据 / 休市 / 无持仓），**不是 0** */
    pnl: number | null;
    /** 色深档位 0/1/2，由 |收益| / 区间内最大值决定（仅 updown 生效） */
    level: 0 | 1 | 2;
    /** 占位空格（日历图首行与周一之前的那几格）：只占位、不画内容 */
    voidCell?: boolean;
    isToday?: boolean;
  }>(),
  { voidCell: false, isToday: false }
);

/** 有真实数值才画金额；`partial` 也照画（值可信，只是不全），其余一律出态标签 */
const hasValue = computed(
  () =>
    props.state === "updown" ||
    props.state === "zero" ||
    props.state === "partial"
);

const isFall = computed(() => props.pnl != null && props.pnl < 0);

/**
 * 文字色用 -ink 级（AA 达标），底色用柔和填充 —— 二者分工见 design.md 涨跌色应用。
 *
 * `partial` 与 `updown` 同用 -ink 级文字：涨跌方向必须可读，区别靠中性底 + 斜纹
 * + 「※」承载，**不能靠降级文字色**（降级后跌破 AA，见 `.is-partial` 注释）。
 * 非盈亏态（未同步 / 无持仓 / 休市）用辅助文字色，与「暂无估值」同一档。
 */
const textColor = computed(() =>
  (props.state === "updown" || props.state === "partial") && props.pnl != null
    ? props.pnl > 0
      ? "var(--color-rise-ink)"
      : "var(--color-fall-ink)"
    : "var(--text-tertiary-ink)"
);
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

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

/* ── 七态视觉 ──
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
   涨跌方向改由 `-ink` 文字色 + 正负号承载，见 textColor。
   与 `zero` 同为灰底、与 `no_price` 同为斜纹，靠**组合**区分三者（灰底+斜纹+「※」）。 */
.is-partial {
  background-color: var(--bg-hover);
  border-color: color-mix(
    in srgb,
    var(--text-tertiary) 30%,
    var(--border-light)
  );
}

/* 用 `::after` 叠加层而不是 `background-image`：`.pnl-calendar__cell` 用了
   `background` 简写，会把 `background-image` 一并重置（同 specificity 下按源码
   顺序输赢，不可靠）。 */
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
    color-mix(in srgb, var(--text-tertiary) 10%, transparent) 8px
  );

  /* 格子有 8px 圆角，叠加层需跟着裁切，否则四角会溢出 */
  border-radius: inherit;
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

/* 未同步：虚线边框——「这里缺了点东西，而且你能处置」。
   #1942 新增：该态原先被并进 `closed`、与「休市」共用空白格，于是
   「净值没同步」在 UI 上读作「市场关门」：一个要去跑同步，一个只能等开盘。
   虚线是「缺了东西」的通用语言，且不依赖任何新色值（禁硬编码色值）。 */
.is-no_data {
  background: transparent;
  border-color: var(--border-default);
  border-style: dashed;
}

/* 无持仓：空白格（同「休市」的留白），靠格内「无持仓」文字自证。
   刻意**不加虚线**：这里没有要处置的问题，把「你没仓位」和「数据有问题」
   画成同一种视觉，只会把「需要行动」的信号稀释掉。 */
.is-no_position {
  background: transparent;
  border-color: var(--border-light);
}

.pnl-calendar__tag {
  font-size: 10px;
  line-height: 1;
  color: var(--text-tertiary-ink);
}

/* partial 的斜纹叠加层是 `z-index: 0`，文字层（日期数字 / 金额 / 态标签）必须抬到
   它之上，否则金额与日期被斜纹盖住。 */
.pnl-calendar__day,
.pnl-calendar__tag,
:deep(.money-display) {
  position: relative;
  z-index: 1;
}

/* 休市：留白，不画任何数字（避免"看起来是 0"） */
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
