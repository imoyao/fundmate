<!--
  PnlCalendarSummary · 收益日历合计行（#980 从 `index.vue` 抽出，纯搬运）

  一行读完，但必须比格子里的小数字更重：它是「这个区间到底赚没赚」的答案，
  是用户扫完整张图后**唯一会去找**的那个数。

  金额（md）与收益率**同时**显示，不随「金额 / 收益率」开关变化——那个开关是针对
  格子里那 30 个小数字的，合计行只有一个数，没必要让它随开关时隐时现（#1942 ②）。
  `range_rate === null` ⇒ 显示「收益率 —」，绝不显示 0.00%：`null` 是「算不出来」
  （区间前一日没有净资产基准），`0` 是「真没赚没赔」，两者必须能区分。

  **为什么是「—」而不是一个数字（2026-11-10 用户裁定）**：年视图的区间起于首个
  流水年份的 1 月 1 日，`range_rate` 的分母 = **区间前一日净资产**，那天账户还没有
  任何持仓 ⇒ 分母结构性地为 0，任何 `pnl / baseline` 都无定义。换分母（TWR /
  累计买入额 / 峰值占用）都能造出一个数字，但同一账本实测差到 2.40% ~ 241.6%
  （口径见 #3037 讨论），属产品决策而非本组件能定的事。故保留「—」，改为把
  **为什么没有**说清楚——占位不给数字，但不再让人猜。分母修好（`net_worth` 纳入
  账户现金）后本行自然出数，无需改这里。
-->
<template>
  <div class="pnl-calendar__summary">
    <span class="pnl-calendar__summary-label">{{ rangeLabel }}合计</span>
    <MoneyDisplay :value="total" size="sm" :show-currency="true" />
    <span class="pnl-calendar__summary-sep" aria-hidden="true">·</span>
    <RiseFallText v-if="rangeRate != null" :value="rangeRate" size="sm" />
    <!-- 不可算时保留「—」，就地写短因；完整成因挂在 title（hover / 读屏都能取到） -->
    <span
      v-else
      class="pnl-calendar__summary-none"
      :title="rateUnavailableReason"
    >
      收益率 —（期初无持仓）
    </span>
    <span class="pnl-calendar__summary-note">
      口径：当日盈亏＝总盈亏变动，存取款不计入
    </span>
  </div>
</template>

<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";

defineOptions({ name: "PnlCalendarSummary" });

defineProps<{
  /** 当前浏览区间的标签（与导航中键、柱状图 aria 共用同一份，由父级算好传入） */
  rangeLabel: string;
  /** 区间合计（元）；`null` = 还没有响应，`MoneyDisplay` 自行显示占位 */
  total: number | null;
  /** 区间收益率（%）；`null` = 算不出来（无基准），渲染「—（期初无持仓）」 */
  rangeRate: number | null;
}>();

/**
 * 「不可算」的完整成因：正文只放短因，这里说清机制。
 * 分母是**区间前一日净资产**，那天还没有持仓 ⇒ 没有可比的基准（不是「没赚钱」）。
 */
const rateUnavailableReason =
  "区间前一日还没有持仓（净资产为 0），没有可比的基准，收益率无从计算";
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* 合计行：一行读完，但必须比格子里的小数字更重。
   现在金额升到 md（16px）并给整行一条极淡的底色带 —— 用底色而不是加边框分隔线，
   是因为这一行已经紧跟在格子下面，再加一条横线会读成「新的一段的表头」。 */
.pnl-calendar__summary {
  display: flex;
  gap: 10px;
  align-items: baseline;
  padding: 8px 10px;
  font-size: var(--text-label);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.pnl-calendar__summary-label {
  font-weight: 500;
  color: var(--text-secondary);
}

/* 金额与收益率之间的分隔点：只做视觉断句，不承载信息（aria-hidden） */
.pnl-calendar__summary-sep {
  color: var(--border-default);
}

/* 「收益率 —（期初无持仓）」：不可算（区间前一日无净资产基准）时的占位，
   与 0.00% 严格区分；括号里的短因是这一行唯一的新增信息，别再让它只剩一个 — */
.pnl-calendar__summary-none {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pnl-calendar__summary-note {
  margin-left: auto;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 响应式：窄屏（弹窗 / 半宽容器）让合计行换行。
   断点走 _breakpoints.scss 单一来源（`bp.below("sm")` = < 640px），
   禁手写像素——guard_breakpoints.py 会拦。
   日历格子的窄屏压缩随其样式一起住在 `PnlCalendarGrid.vue`。 */
@include bp.below("sm") {
  .pnl-calendar__summary {
    flex-wrap: wrap;
  }

  .pnl-calendar__summary-note {
    width: 100%;
    margin-left: 0;
  }
}
</style>
