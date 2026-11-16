<template>
  <!-- #3135：这些持仓账上还有份额，名下流水却已经卖掉（挂回流水按契约不重算份额）。
       卡片上的「理论 0 / 实际 1000」只报差额，说不出这 1000 从哪来——这里把成因
       （含对账补录流水）和可执行动作一起摆出来，否则用户唯一想得到的就是再补录一笔。 -->
  <section class="share-integrity" aria-label="份额与流水不自洽">
    <header class="share-integrity__head">
      <h3 class="share-integrity__title">
        份额与流水不自洽 · {{ items.length }} 条
      </h3>
      <p class="share-integrity__desc">
        这些持仓账上还有份额，但名下流水已经卖掉：挂回流水只改归属、不会自动重算份额。
      </p>
    </header>

    <ul class="share-integrity__list">
      <li
        v-for="item in items"
        :key="item.position_id"
        class="share-integrity__row"
      >
        <div class="share-integrity__row-title">
          <span class="share-integrity__name">
            {{ reconGroupTitle(item.symbol, item.name) }}
            <span class="share-integrity__symbol">
              {{ reconSymbolCode(item.symbol) }}
            </span>
          </span>
          <el-tag
            v-if="item.adjustment_txns.length"
            type="warning"
            size="small"
          >
            含 {{ item.adjustment_txns.length }} 笔对账补录
          </el-tag>
          <el-tag
            v-else-if="item.flow_state === 'oversold'"
            type="danger"
            size="small"
          >
            超卖
          </el-tag>
        </div>

        <p class="share-integrity__nums">
          <span
            >账上 <b>{{ reconQuantity(item.quantity_now) }}</b></span
          >
          <span
            >按流水
            <b>{{ reconQuantity(item.quantity_if_recomputed) }}</b></span
          >
          <span
            >差 <b>{{ reconQuantity(item.diff) }}</b></span
          >
        </p>

        <ul v-if="item.adjustment_txns.length" class="share-integrity__txns">
          <li
            v-for="txn in item.adjustment_txns"
            :key="txn.id"
            class="share-integrity__txn"
          >
            #{{ txn.id }} {{ txnTypeLabel(txn.txn_type) }}
            {{ reconQuantity(txn.quantity) }} ·
            {{ txn.trade_date || "日期未记录" }}
          </li>
        </ul>

        <p class="share-integrity__hint">{{ item.remedy.hint }}</p>

        <div class="share-integrity__actions">
          <el-button
            v-if="item.adjustment_txns.length"
            size="small"
            @click="emit('go-transactions', item)"
          >
            去核对补录流水
          </el-button>
          <el-button
            v-else
            size="small"
            type="primary"
            plain
            :loading="actingId === item.position_id"
            @click="emit('recompute', item)"
          >
            按流水重算份额
          </el-button>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import type { ShareIntegrityItem } from "@/api/reconciliation";
import {
  reconGroupTitle,
  reconQuantity,
  reconSymbolCode
} from "../utils/reconDisplay";

defineOptions({ name: "ShareIntegrityPanel" });

defineProps<{
  items: ShareIntegrityItem[];
  /** 正在重算的持仓 id（只锁住那一行，不整块禁用） */
  actingId?: number | null;
}>();

const emit = defineEmits<{
  (e: "recompute", item: ShareIntegrityItem): void;
  (e: "go-transactions", item: ShareIntegrityItem): void;
}>();

/** 补录流水只有买/卖两种来源（对账补录的现金类不走份额），其余原样显示代码。 */
function txnTypeLabel(txnType: string): string {
  if (txnType === "sell") return "卖出";
  if (txnType === "buy") return "买入";
  return txnType;
}
</script>

<style scoped>
.share-integrity {
  padding: var(--space-3) var(--space-standard);
  margin-bottom: var(--space-standard);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-left: 3px solid var(--color-warning);
  border-radius: var(--radius-card);
}

.share-integrity__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.share-integrity__title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.share-integrity__desc,
.share-integrity__hint {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

.share-integrity__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 0;
  margin: var(--space-3) 0 0;
  list-style: none;
}

.share-integrity__row {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-subtle);
}

.share-integrity__row:first-child {
  padding-top: 0;
  border-top: none;
}

.share-integrity__row-title {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.share-integrity__name {
  font-weight: 600;
  color: var(--text-primary);
}

.share-integrity__symbol {
  margin-left: var(--space-1);
  font-size: var(--text-label);
  font-weight: 400;
  color: var(--text-secondary);
}

.share-integrity__nums {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin: 0;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.share-integrity__nums b {
  font-weight: 600;
  color: var(--text-primary);
}

.share-integrity__txns {
  padding-left: var(--space-3);
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
  list-style: disc;
}

.share-integrity__actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-1);
}
</style>
