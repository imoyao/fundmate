<script setup lang="ts">
// 交易流水·表格视图（含分页与空态）。状态与取数都在父层，这里只渲染 + 上抛翻页与编辑。
//
// #2712 收编：此前这里是**第四套**交易表格 —— 表头「操作」既指交易类型又指行操作、
// 日期原样打印接口值（`2026-06-03T00:00:00`）、金额/手续费的对齐与账本 Tab 各写各的。
// 用户看到的是「同一批流水在不同页面长得不一样」。现在表格骨架、列序、对齐、
// 日期与价格精度全部交给 `components/TransactionTable`，本组件只留容器职责。
import { computed } from "vue";
import type { TransactionRecord } from "@/api/transactions";
import { IconifyIconOffline } from "@/components/ReIcon";
import TransactionTable, {
  type TransactionRow
} from "@/components/TransactionTable/index.vue";

const props = defineProps<{
  transactions: TransactionRecord[];
  loading: boolean;
  total: number;
  currentPage: number;
  pageSize: number;
}>();

const emit = defineEmits<{
  "page-change": [page: number];
  "size-change": [size: number];
  edit: [row: TransactionRow];
}>();

/**
 * 行适配：`/api/transactions` 的字段名与 `TransactionRow` 同名（type / trade_date /
 * price / quantity / amount / fee / status / notes / symbol），只把 `null` 归一成
 * `undefined`（`TransactionRow.symbol` 是可选字符串，ProductDisplay 收到 null 会渲染 `# --`）。
 * 页面已由后端按「交易日优先、确认日兜底」排序，这里不再重排。
 */
const rows = computed<TransactionRow[]>(() =>
  props.transactions.map(t => ({ ...t, symbol: t.symbol ?? undefined }))
);

/** 编辑弹窗需要原始记录（含 ledger_id / source 等），按 id 回查 */
function onEdit(row: TransactionRow) {
  const original = props.transactions.find(t => t.id === row.id);
  emit("edit", (original ?? row) as unknown as TransactionRow);
}
</script>

<template>
  <!-- 加载态留在容器（原表格自带 v-loading，收编到共享组件后不能丢） -->
  <el-card v-loading="loading" shadow="never">
    <TransactionTable
      :rows="rows"
      mode="full"
      show-asset
      show-fee
      show-status
      show-notes
      show-edit
      sortable
      @edit="onEdit"
    />

    <!-- 分页 -->
    <div v-if="total > 0" class="flex justify-end mt-4">
      <el-pagination
        background
        layout="prev, pager, next, sizes, total"
        :total="total"
        :current-page="currentPage"
        :page-size="pageSize"
        :page-sizes="[5, 10, 20, 50]"
        @current-change="page => emit('page-change', page)"
        @size-change="size => emit('size-change', size)"
      />
    </div>

    <div
      v-if="!loading && transactions.length === 0"
      class="text-center py-12 text-gray-400"
    >
      <IconifyIconOffline icon="ep:folder-opened" class="text-4xl mb-2" />
      <p>暂无交易记录</p>
      <p class="text-sm mt-1">记账后交易流水会出现在这里</p>
    </div>
  </el-card>
</template>
