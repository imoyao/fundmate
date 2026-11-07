<template>
  <article class="olg-group">
    <header class="olg-group__head">
      <div class="olg-group__title">
        <span class="olg-group__key">
          {{ group.resolved_ledger?.name || "无法归属" }}
        </span>
        <span class="olg-group__sub">
          {{ group.txn_count }} 条流水 · {{ group.batch_label }}
        </span>
      </div>
      <el-button
        size="small"
        type="primary"
        plain
        :disabled="!fixable"
        @click="emit('fix', group)"
      >
        逐条核对并回填
      </el-button>
    </header>

    <!-- 不可回填必须说清「差什么」，不能只把按钮置灰让用户猜 -->
    <p v-if="group.block_reason" class="olg-group__block">
      {{ group.block_reason }}
    </p>

    <p v-if="group.resolved_ledger" class="olg-group__meta">
      目标账本 #{{ group.resolved_ledger.id }}（{{
        group.resolved_ledger.name
      }}） · 按账户名精确同名唯一判定
    </p>

    <!-- 逐条明细：每条都带后端解析出的归属与 blocked 原因 -->
    <el-collapse class="olg-collapse">
      <el-collapse-item :name="group.key">
        <template #title>
          查看 {{ group.transactions.length }} 条流水明细
        </template>
        <ul class="olg-txns">
          <li v-for="t in group.transactions" :key="t.id" class="olg-txn">
            <span class="olg-txn__id">#{{ t.id }} {{ t.txn_type }}</span>
            <span>{{ t.trade_date || "缺交易日期" }}</span>
            <span>{{ t.account_name || "缺账户名" }}</span>
            <span>{{ t.amount }} 元</span>
            <span v-if="t.block_reason" class="olg-txn__block">
              {{ t.block_reason }}
            </span>
            <span v-else class="olg-txn__ok">
              → #{{ t.resolved_ledger_id }}
            </span>
          </li>
        </ul>
      </el-collapse-item>
    </el-collapse>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { OrphanLedgerGroup } from "@/api/reconciliation";

/** 域 G 单个归属分组卡（#2875）：只展示后端扫描结果，写动作交给弹窗。 */
const props = defineProps<{ group: OrphanLedgerGroup }>();
const emit = defineEmits<{ fix: [group: OrphanLedgerGroup] }>();

/** 组级与逐条两级都看，避免组级概括说明把 blocked 行藏起来 */
const fixable = computed(
  () =>
    props.group.block_reason === null &&
    props.group.transactions.length > 0 &&
    props.group.transactions.every(t => t.block_reason === null)
);
</script>

<style scoped>
.olg-group {
  padding: 12px 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.olg-group__head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.olg-group__title {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
  min-width: 0;
}

.olg-group__key {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-primary-ink);
}

.olg-group__sub,
.olg-group__meta {
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.olg-group__meta {
  margin: 6px 0;
}

.olg-group__block {
  padding: 6px 10px;
  margin: 6px 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: color-mix(in srgb, var(--color-warning-ink) 10%, transparent);
  border-radius: var(--radius-sm);
}

.olg-txns {
  padding-left: 18px;
  margin: 6px 0 0;
}

.olg-txn {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  padding: 3px 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.olg-txn__id {
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.olg-txn__block {
  color: var(--color-warning-ink);
}

.olg-txn__ok {
  font-variant-numeric: tabular-nums;
  color: var(--color-success-ink);
}
</style>
