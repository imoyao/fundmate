<!--
  PnlCalendarSummary · 收益日历合计行（#980 从 `index.vue` 抽出，纯搬运）

  一行读完，但必须比格子里的小数字更重：它是「这个区间到底赚没赚」的答案，
  是用户扫完整张图后**唯一会去找**的那个数。

  金额（md）与收益率**同时**显示，不随「金额 / 收益率」开关变化——那个开关是针对
  格子里那 30 个小数字的，合计行只有一个数，没必要让它随开关时隐时现（#1942 ②）。
  `range_rate === null` ⇒ 显示「收益率 —」，绝不显示 0.00%：`null` 是「算不出来」
  （区间前一天没有基准），`0` 是「真没赚没赔」，两者必须能区分。
-->
<template>
  <div class="pnl-calendar__summary">
    <span class="pnl-calendar__summary-label">{{ rangeLabel }}合计</span>
    <MoneyDisplay :value="total" size="sm" :show-currency="true" />
    <span class="pnl-calendar__summary-sep" aria-hidden="true">·</span>
    <RiseFallText v-if="rangeRate != null" :value="rangeRate" size="sm" />
    <span v-else class="pnl-calendar__summary-none">收益率 —</span>
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
  /** 区间收益率（%）；`null` = 算不出来（无基准），显示「—」 */
  rangeRate: number | null;
}>();
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

/* 「收益率 —」：不可算（缺区间前一天基准）时的占位，与 0.00% 严格区分 */
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
