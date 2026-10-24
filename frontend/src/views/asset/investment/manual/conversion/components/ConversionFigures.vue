<script setup lang="ts">
/**
 * 三个数（转换确认页 / 结果页共用，#980 拆分自 ConversionForm.vue）。
 *
 * 两处版式**必须一模一样**：结果页是「刚才那三个数的回执」，
 * 用户在这里核对的正是「和确认页对不对得上」。原先这份 30 行结构写了两遍，
 * 一处改字号、另一处忘改就会让回执和确认单对不上——所以收成一个组件，
 * 差异只有数据来源（确认页读 `estimate`，结果页读 `result`）。
 *
 * 净值走 `@/utils/pricePrecision` 契约（基金 4 位），不在这里写死小数位：
 * 位数是展示契约的一部分，硬编码在模板里会绕开 `scripts/guard_price_precision.mjs`。
 */
import type { ConversionEstimateResult } from "@/api/positions";
import { formatPrice } from "@/utils/pricePrecision";

defineProps<{
  /** 转出腿（确认页的 `estimate.out` / 结果页的 `result.out`） */
  out: ConversionEstimateResult["out"];
  /** 净转入金额：确认页取 `estimate.net_amount`，结果页取 `result.in.amount` */
  netAmount: number;
  /** 转入份额（预估 / 实际确认） */
  inQuantity: number;
}>();
</script>

<template>
  <div class="figure-grid">
    <div class="figure">
      <div class="figure__label">转出金额</div>
      <div class="figure__value">¥{{ out.amount.toFixed(2) }}</div>
      <div class="figure__aside">
        {{ out.quantity.toFixed(2) }} 份 × 净值
        {{ formatPrice(out.nav, "fund") }}
      </div>
    </div>
    <div class="figure">
      <div class="figure__label">费用合计</div>
      <div class="figure__value">
        <!-- 0 费用不写成「−¥0.00」：负零在中文界面上读作「倒扣了零头」 -->
        {{ out.fee > 0 ? "−" : "" }}¥{{ out.fee.toFixed(2) }}
      </div>
      <div class="figure__aside">
        赎回 {{ out.fee_breakdown.redeem.toFixed(2) }} · 补差
        {{ out.fee_breakdown.compensate.toFixed(2) }}
      </div>
    </div>
    <div class="figure figure--net">
      <div class="figure__label">净转入</div>
      <div class="figure__value">¥{{ netAmount.toFixed(2) }}</div>
      <div class="figure__aside">预估 {{ inQuantity.toFixed(2) }} 份</div>
    </div>
  </div>
</template>

<style scoped>
/* 三个数：核对时真正要比的就是这三个，字号拉开才有主次。
   确认页与结果页共用（结果页是「刚才那三个数的回执」，版式必须一模一样）。
   数字字号走字阶令牌 --text-num-hero，不写 22px 这类字面值（#2323）。 */
.figure-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.figure {
  padding: 12px 14px;
  background: var(--bg-soft);
  border-radius: var(--radius-md);
}

.figure__label {
  margin-bottom: 6px;
  font-size: var(--text-label);
  line-height: 1.4;
  color: var(--text-secondary);
}

.figure__value {
  font-size: var(--text-num-hero);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  color: var(--text-primary);
  letter-spacing: -0.2px;
}

/* 净转入 = 这笔操作到手的结果，用品牌文字色标出来。
   不用 --color-rise：红涨绿跌是行情语义，这里表达的是金额层级 */
.figure--net .figure__value {
  color: var(--brand-ink);
}

.figure__aside {
  margin-top: 4px;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  line-height: 1.4;
  color: var(--text-tertiary-ink);
}
</style>
