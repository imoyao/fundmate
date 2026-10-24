<script setup lang="ts">
// 交易流水·表格视图（含分页与空态）。
// 状态与取数都在父层，这里只渲染 + 上抛翻页与编辑。
import type { TransactionRecord } from "@/api/transactions";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { txnTypeLabel } from "@/constants";
import { statusLabel, statusTag, typeTag } from "./transactionListModel";

defineProps<{
  transactions: TransactionRecord[];
  loading: boolean;
  total: number;
  currentPage: number;
  pageSize: number;
}>();

const emit = defineEmits<{
  "page-change": [page: number];
  "size-change": [size: number];
  edit: [row: any];
}>();
</script>

<template>
  <el-card shadow="never">
    <el-table
      v-loading="loading"
      :data="transactions"
      stripe
      size="default"
      :default-sort="{ prop: 'created_at', order: 'descending' }"
    >
      <el-table-column prop="position_name" label="资产名称" min-width="150">
        <template #default="{ row }">
          <div :class="{ 'opacity-50 grayscale': row.position_id === null }">
            <p class="font-medium text-gray-800">{{ row.position_name }}</p>
            <p v-if="row.position_id === null" class="text-xs text-gray-400">
              已删除
            </p>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="type" label="操作" width="90">
        <template #default="{ row }">
          <el-tag :type="typeTag(row.type)" size="small" effect="plain">
            {{ txnTypeLabel(row.type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="amount" label="金额" width="120" align="right">
        <template #default="{ row }">
          <MoneyDisplay :value="row.amount" :show-sign="false" size="sm" />
        </template>
      </el-table-column>
      <el-table-column prop="fee" label="手续费" width="90" align="right">
        <template #default="{ row }">
          <MoneyDisplay :value="row.fee" :show-sign="false" size="sm" />
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small" effect="plain">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="trade_date" label="交易日期" width="110" />
      <el-table-column prop="account_name" label="账户/渠道" width="110" />
      <el-table-column prop="notes" label="备注" min-width="120">
        <template #default="{ row }">
          <span class="text-gray-400">{{ row.notes || "-" }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="64" align="center">
        <template #default="{ row }">
          <el-button
            size="small"
            text
            type="primary"
            @click="emit('edit', row)"
          >
            编辑
          </el-button>
        </template>
      </el-table-column>
    </el-table>

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
