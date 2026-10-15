<template>
  <!-- 交易记录 Tab -->
  <el-tab-pane label="交易记录" name="transactions">
    <!-- 表格本体走全站统一的 TransactionTable（#2104 验收「同一组件，禁止
         第二套实现」）：此前详情页 / 账本 Tab / 持仓抽屉三套表格，字段名
         （type vs txn_type）、日期口径（trade_date vs confirm_date）、类型
         着色、手续费列全不一致。本容器只负责分页与行操作。 -->
    <TransactionTable
      :rows="rows"
      mode="full"
      show-asset
      show-fee
      show-edit
      show-delete
      sortable
      @edit="onEdit"
      @delete="onDelete"
    />
    <div
      v-if="p.transactionsTotal === 0"
      class="text-center py-8"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      暂无交易记录
    </div>
    <div v-if="p.transactionsTotal > 0" class="flex justify-end mt-4">
      <el-pagination
        v-model:current-page="p.transactionsPage"
        :page-size="p.transactionsPageSize"
        layout="prev, pager, next"
        :total="p.transactionsTotal"
        small
        @current-change="p.loadTransactions"
      />
    </div>
  </el-tab-pane>
</template>

<script setup lang="ts">
import { computed, reactive } from "vue";
import TransactionTable, {
  type TransactionRow
} from "@/components/TransactionTable/index.vue";
import type { LedgerTxnRow } from "@/composables/useLedgerTransactions";
import type { useLedgerDetailPage } from "../composables/useLedgerDetailPage";

defineOptions({ name: "LedgerDetailTransactionsPane" });

// #980 P1-C 拆分自 detail.vue：交易记录 Tab 面板（公共表格 + 分页 + 行操作）。
// 行适配：LedgerTxnRow.txn_type → TransactionRow.type（字段名唯一分歧，
// 其余字段同名）。emit 回传的是适配行，操作前按 id 找回原行给 page 层。
const props = defineProps<{ page: ReturnType<typeof useLedgerDetailPage> }>();
const p = reactive(props.page);

const rows = computed<TransactionRow[]>(() =>
  p.transactionsList.map(r => ({ ...r, type: r.txn_type }))
);

function onEdit(row: TransactionRow) {
  const original = p.transactionsList.find(
    (r: LedgerTxnRow) => r.id === row.id
  );
  if (original) p.openEditTxnDialog(original);
}

function onDelete(row: TransactionRow) {
  const original = p.transactionsList.find(
    (r: LedgerTxnRow) => r.id === row.id
  );
  if (original) void p.confirmDeleteTxn(original);
}
</script>
