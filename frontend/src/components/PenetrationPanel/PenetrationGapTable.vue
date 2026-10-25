<!--
  未穿透构成表（#2617 拆出）。

  **逐条带 reason**，把「本质无股票敞口」与「待补真缺口」分开呈现：不做归一化、
  不摊到行业上——那会把 86% 仓位的基金显示成满仓（D45 口径陷阱 ③）。

  为什么是子组件：`PenetrationPanel` 触到 `check_vue_size` 的 400 行阈值（#980）。
-->
<template>
  <div>
    <h4 class="panel-subtitle">未穿透构成</h4>
    <p
      v-if="!rows.length"
      class="text-sm"
      :style="{ color: 'var(--text-secondary)' }"
    >
      全部持仓均已穿透。
    </p>
    <table v-else class="unpen-table">
      <thead>
        <tr>
          <th>标的</th>
          <th class="num">市值</th>
          <th class="num">占比</th>
          <th>原因</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="`${row.asset_type}-${row.symbol}`">
          <td>{{ row.name }}</td>
          <td class="num" :style="{ color: 'var(--text-primary)' }">
            {{ formatAmount(row.value_cny) }}
          </td>
          <td class="num" :style="{ color: 'var(--text-secondary)' }">
            {{ percent(row.ratio_of_total) }}
          </td>
          <td>
            <span
              class="reason-tag"
              :class="{ 'reason-tag--gap': row.reason !== 'cash_equivalent' }"
            >
              {{ row.reason_label }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { percent } from "./format";
import { formatAmount } from "@/utils/currency";
import type { PenetrationUnpenetrated } from "@/api/summary";

defineProps<{ rows: PenetrationUnpenetrated[] }>();
</script>

<style scoped>
.panel-subtitle {
  margin: 0 0 var(--space-compact);
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.unpen-table {
  width: 100%;
  font-size: var(--text-small);
  border-collapse: collapse;
}

.unpen-table th,
.unpen-table td {
  padding: var(--space-compact) 0;
  text-align: left;
  border-bottom: 1px solid var(--border-light);
}

.unpen-table th {
  font-weight: 500;
  color: var(--text-tertiary);
}

.unpen-table .num {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.reason-tag {
  display: inline-block;
  padding: 1px var(--space-compact);
  color: var(--text-secondary);
  background: var(--bg-muted);
  border-radius: var(--radius-button);
}

.reason-tag--gap {
  color: var(--color-warning, var(--text-secondary));
  background: var(--color-warning-20, var(--bg-muted));
}
</style>
