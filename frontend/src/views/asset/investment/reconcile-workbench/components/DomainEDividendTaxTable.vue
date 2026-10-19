<template>
  <div class="domain-e-body">
    <el-empty
      v-if="!loading && items.length === 0"
      description="没有待补记的分红扣税"
      :image-size="80"
    />
    <div v-else v-loading="loading" class="tax-list">
      <!-- 口径说明：用户最容易误读的是「为什么系统不直接替我算」。
           这句话必须出现在列表之前，而不是藏在文档里。 -->
      <p class="tax-note">
        A
        股红利税按<strong>实际持股期</strong>在卖出时补扣，税率取决于买入批次，
        本系统只有聚合持仓，因此不自动推算。下列为「该标的该年有现金分红、
        却没有扣税流水」的项——请到券商交割单核对后，在流水里补记一笔「扣税」。
      </p>

      <article
        v-for="it in items"
        :key="`${it.symbol}-${it.year}`"
        class="tax-item"
      >
        <header class="tax-item__head">
          <span class="tax-item__symbol">{{ it.symbol }}</span>
          <span class="tax-item__name">{{ it.name || "—" }}</span>
          <span class="tax-item__year">{{ it.year }} 年</span>
        </header>
        <p class="tax-item__meta">
          现金分红合计
          <span class="tax-item__amount">{{ yuan(it.dividend_cents) }} 元</span>
          · 共 {{ it.dividend_count }} 笔
          <template v-if="it.account_name"> · {{ it.account_name }}</template>
          <template v-if="it.last_dividend_on">
            · 最近一笔 {{ formatDate(it.last_dividend_on) }}</template
          >
        </p>
      </article>

      <p v-if="totalCents > 0" class="tax-total">
        合计 {{ items.length }} 项，分红 {{ yuan(totalCents) }} 元（均为税前）
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatDate } from "@/utils/date";
import type { DividendTaxPendingItem } from "@/api/reconciliation";

/**
 * 域 E：分红未记扣税（#541）。
 *
 * WHY 不复用 `DomainBDiscTable`：域 B 的行是「应然 vs 实然，算出差额」——
 * 本域**没有应然值可算**（我们不推算税率），硬套会造出一列假的「应有税额」，
 * 那正是这次刻意不做的事。所以这里只陈述账内已有事实（分了多少、什么时候），
 * 把「该扣多少」留给用户从交割单读回来。
 */
defineProps<{
  items: DividendTaxPendingItem[];
  totalCents: number;
  loading: boolean;
}>();

/** 分 → 元（保留两位）。后端金额一律整数分，前端不做二次运算以外的加工。 */
function yuan(cents: number): string {
  return (cents / 100).toFixed(2);
}
</script>

<style scoped>
.domain-e-body {
  padding: 4px 0;
}

.tax-note {
  margin: 0 0 12px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.tax-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.tax-item:last-of-type {
  border-bottom: none;
}

.tax-item__head {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.tax-item__symbol {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.tax-item__name {
  color: var(--el-text-color-regular);
}

.tax-item__year {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tax-item__meta {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.tax-item__amount {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--el-color-warning);
}

.tax-total {
  margin: 12px 0 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
