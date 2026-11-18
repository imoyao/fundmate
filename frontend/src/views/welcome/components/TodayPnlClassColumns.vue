<!--
  TodayPnlClassColumns · 当日收益卡的两列分项（股票 / 基金）

  标题只写「股票」「基金」（2026-11-06 用户拍板，D91）：用户日常不按交易所
  场所叫资产，把「含 ETF、可转债」这类集合边界塞进标题会显得繁琐；
  边界统一放在两列下方的一行小字里，一眼可扫、不占标题层级。

  为什么这两列与 hero 能写得这么「敢」：它们是**同一份数据**的两个切面
  （后端 `Σ classes.pnl ≡ total_pnl`），前端不做第二次相加；占比也一律后端直出
  （`share_of_invested`），列内不做除法。

  数字跳动（用户要求「不打扰」）：只有这两列的盈亏做 420ms 缓动，市值直接落值——
  市值是稳定锚点，跟着一起动会显得整张卡在抖。

  空态不写 0：`classes` 为空时说明「还没有可估值的持仓」，填 0 会把「不知道」
  画成「没赚没亏」。
-->
<template>
  <div v-if="classes.length" class="cls">
    <div v-for="item in classes" :key="item.key" class="cls__col">
      <p class="cls__label">{{ item.label }}</p>
      <div class="cls__value">
        <MoneyDisplay
          :value="tweenOf(item.key)"
          size="lg"
          :show-currency="false"
          empty-text="—"
        />
        <span
          v-if="item.rate != null"
          class="cls__rate"
          :class="rateClass(item.rate)"
          >{{ signedRate(item.rate) }}</span
        >
      </div>
      <div class="cls__foot">
        <MoneyDisplay
          :value="item.market_value"
          size="sm"
          :show-sign="false"
          :auto-color="false"
          custom-color="var(--text-tertiary-ink)"
        />
        <span v-if="item.share_of_invested != null" class="cls__share"
          >占投资 {{ pct1(item.share_of_invested) }}</span
        >
      </div>
    </div>
    <p class="cls__hint">
      股票含 ETF、可转债；基金仅含场外基金（不含货币基金）
    </p>
  </div>

  <p v-else class="cls__empty" :style="{ color: 'var(--text-tertiary-ink)' }">
    还没有可估值的股票或基金持仓
  </p>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { useTweenNumber } from "@/composables/useTweenNumber";
import type { TodayPnlClass } from "@/api/summary";
import { pct1, rateClass, signedRate } from "../composables/pnlFormat";

defineOptions({ name: "TodayPnlClassColumns" });

const props = defineProps<{
  classes: TodayPnlClass[];
}>();

const pnlOf = (key: TodayPnlClass["key"]) =>
  props.classes.find(item => item.key === key)?.pnl ?? null;

const stockTween = useTweenNumber(computed(() => pnlOf("stock")));
const fundTween = useTweenNumber(computed(() => pnlOf("fund")));

const tweenOf = (key: TodayPnlClass["key"]) =>
  key === "stock" ? stockTween.value : fundTween.value;
</script>

<style lang="scss" scoped>
/* 两列分项：竖线是同级弱分隔（--border-subtle），比外框横线轻一档 */
.cls {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.cls__col {
  min-width: 0;
  padding: 0 var(--space-compact);
}

.cls__col:first-child {
  padding-left: 0;
}

.cls__col + .cls__col {
  border-left: 1px solid var(--border-subtle);
}

.cls__label {
  display: flex;
  gap: 6px;
  align-items: center;
  margin: 0 0 6px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.cls__value {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin-bottom: 4px;
}

.cls__rate {
  font-size: var(--text-small, 14px);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* 分项脚注：市值在左、占比在右。原先市值孤零零挂在列左，右半列是空的；
   占比填进这个空位，同时回答「股票和基金谁占大头」。 */
.cls__foot {
  display: flex;
  gap: var(--space-2, 8px);
  align-items: baseline;
  justify-content: space-between;
}

.cls__share {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

/* 集合边界只占一行小字：跨两列、次级墨色，不参与数字层级 */
.cls__hint {
  grid-column: 1 / -1;
  margin: 8px 0 0;
  font-size: var(--text-label);
  line-height: 1.4;
  color: var(--text-tertiary-ink);
}

.cls__empty {
  margin: 0;
  font-size: var(--text-small);
}

.is-rise {
  color: var(--color-rise-ink);
}

.is-fall {
  color: var(--color-fall-ink);
}

.is-zero {
  color: var(--text-secondary);
}
</style>
