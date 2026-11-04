<script setup lang="ts">
/**
 * 交易流水 · 账户单元格（可点胶囊 / 未归属虚线）。
 *
 * 「这笔钱在哪个账户」是核对流水时最常问的第二句话。此前表格连账户列都没有，
 * 流水线里只是「账户：xxx」纯文本——知道而不给跳转，等于让用户自己去账户页翻。
 *
 * ## 为什么可点与不可点必须长得不一样
 *
 * 有 `ledger_id` 才是真落点；没有的（探市录入、导入时未归档）**不伪装成链接**：
 * 虚线 + 次要字色 + `title` 说明不可跳转。否则用户点了没反应，会以为页面坏了。
 */
import { computed } from "vue";
import type { TransactionRow } from "./model";

const props = defineProps<{ row: TransactionRow }>();

const hasLedger = computed(() => Boolean(props.row.ledger_id));

/**
 * 展示名：未归档时不说「未知账户」——那是把「没归档」说成「不知道」，而库里其实
 * 存着当时的账户名快照。只有快照也空时才退到「未归属账户」。
 */
const name = computed(() => {
  const snapshot = (props.row.account_name ?? "").trim();
  if (hasLedger.value) return snapshot || "未知账户";
  return snapshot && snapshot !== "未知账户" ? snapshot : "未归属账户";
});

const linkTitle = computed(() => `前往账户「${name.value}」`);
</script>

<template>
  <router-link
    v-if="hasLedger"
    class="txn-account"
    :to="`/asset/ledgers/${row.ledger_id}`"
    :title="linkTitle"
  >
    <span class="txn-account__name">{{ name }}</span>
    <span class="txn-account__arrow" aria-hidden="true">›</span>
  </router-link>
  <span
    v-else
    class="txn-account txn-account--loose"
    title="这笔流水未归档到账户，无法跳转"
    >{{ name }}</span
  >
</template>

<style scoped>
.txn-account {
  display: inline-flex;
  gap: 2px;
  align-items: baseline;
  max-width: 100%;
  font-size: inherit;
  color: var(--text-primary);
  text-decoration: none;
}

.txn-account__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 箭头只在可跳转时出现：它是「有地方可去」的视觉承诺 */
.txn-account__arrow {
  color: var(--text-tertiary-ink);
}

.txn-account:hover .txn-account__name {
  color: var(--color-primary-ink);
  border-bottom: 1px solid currentColor;
}

/* 未归属：虚线表示「这里本该有个落点，但没有」——不伪装成链接 */
.txn-account--loose {
  color: var(--text-tertiary-ink);
  cursor: default;
  border-bottom: 1px dashed var(--border-light);
}
</style>
