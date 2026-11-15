<!--
  未穿透构成表（#2617 拆出）。

  **逐条带 reason**，把「本质无股票敞口」与「待补真缺口」分开呈现：不做归一化、
  不摊到行业上——那会把 86% 仓位的基金显示成满仓（D45 口径陷阱 ③）。

  为什么是子组件：`PenetrationPanel` 触到 `check_vue_size` 的 400 行阈值（#980）。

  2026-11-15 折叠：这张表此前**全量铺开**——账户 id=12 实测 123 行、4860px，
  占整页 36%。其中 118 行是同一句「基金季报未披露」，逐行读完也拿不到新信息。
  现在默认只给前 5 行（金额最大的那些）+ 总项数/总额，需要时再展开。
-->
<template>
  <div>
    <div class="gap-head">
      <h4 class="panel-subtitle">未穿透构成</h4>
      <p v-if="rows.length" class="gap-head__meta">
        {{ rows.length }} 项 · {{ formatAmount(total) }}
      </p>
    </div>
    <p
      v-if="!rows.length"
      class="text-sm"
      :style="{ color: 'var(--text-secondary)' }"
    >
      全部持仓均已穿透。
    </p>
    <template v-else>
      <table class="detail-table">
        <thead>
          <tr>
            <th>标的</th>
            <th class="detail-table__num">市值</th>
            <th class="detail-table__num">占比</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in shownRows" :key="`${row.asset_type}-${row.symbol}`">
            <td>{{ row.name }}</td>
            <td
              class="detail-table__num"
              :style="{ color: 'var(--text-primary)' }"
            >
              {{ formatAmount(row.value_cny) }}
            </td>
            <td
              class="detail-table__num"
              :style="{ color: 'var(--text-secondary)' }"
            >
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
      <el-button
        v-if="rows.length > LIMIT"
        text
        size="small"
        class="gap-toggle"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{
          expanded
            ? "收起明细"
            : `展开其余 ${rows.length - shownRows.length} 项`
        }}
      </el-button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { percent } from "./format";
import { formatAmount } from "@/utils/currency";
import type { PenetrationUnpenetrated } from "@/api/summary";

const props = defineProps<{ rows: PenetrationUnpenetrated[] }>();

/** 折叠前显示的行数：够看清「大头是谁」，又不至于把整页撑长。 */
const LIMIT = 5;

const expanded = ref(false);

const shownRows = computed(() =>
  expanded.value ? props.rows : props.rows.slice(0, LIMIT)
);

const total = computed(() =>
  props.rows.reduce((sum, row) => sum + (row.value_cny ?? 0), 0)
);
</script>

<style scoped>
.gap-head {
  display: flex;
  gap: var(--space-compact);
  align-items: baseline;
  justify-content: space-between;
}

.gap-head__meta {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.gap-toggle {
  padding: 0;
  margin-top: var(--space-compact);
}

.panel-subtitle {
  margin: 0 0 var(--space-compact);
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
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
