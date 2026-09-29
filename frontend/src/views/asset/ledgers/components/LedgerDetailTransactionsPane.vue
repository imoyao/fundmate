<template>
  <!-- 交易记录 Tab -->
  <el-tab-pane label="交易记录" name="transactions">
    <el-table
      :data="p.transactionsList"
      stripe
      size="default"
      :default-sort="{ prop: 'confirm_date', order: 'descending' }"
    >
      <el-table-column prop="confirm_date" label="日期" width="110" sortable>
        <template #default="{ row }">{{
          formatDate(row.confirm_date)
        }}</template>
      </el-table-column>
      <!-- 资产列宽统一 160（产品信息列宽度规范，见 docs/design/components.md） -->
      <el-table-column label="资产名称" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="txn-asset-name">{{ row.position_name }}</span>
          <span v-if="row.symbol" class="txn-asset-code">{{ row.symbol }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <span :class="p.getTxnTypeClass(row.txn_type)">{{
            txnTypeLabel(row.txn_type)
          }}</span>
        </template>
      </el-table-column>
      <el-table-column label="价格" width="100" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.price || 0"
            :precision="pricePrecision(row.asset_type)"
            :show-sign="false"
            :show-currency="false"
            size="sm"
          />
        </template>
      </el-table-column>
      <el-table-column label="数量" width="80" align="right">
        <template #default="{ row }">{{ row.quantity }}</template>
      </el-table-column>
      <el-table-column
        label="金额"
        width="120"
        align="right"
        sortable
        prop="amount"
      >
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.amount || 0"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </template>
      </el-table-column>
      <el-table-column label="手续费" width="80" align="right" prop="fee">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.fee || 0"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </template>
      </el-table-column>
      <el-table-column
        v-if="!p.isUnclassified"
        label="操作"
        width="140"
        fixed="right"
      >
        <template #default="{ row }">
          <div class="flex items-center gap-1" style="white-space: nowrap">
            <el-button
              text
              size="small"
              @click.stop="p.openEditTxnDialog(row as LedgerTxnRow)"
              >编辑</el-button
            >
            <el-button
              text
              size="small"
              type="danger"
              @click.stop="p.confirmDeleteTxn(row as LedgerTxnRow)"
              >删除</el-button
            >
          </div>
        </template>
      </el-table-column>
    </el-table>
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
import { reactive } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { txnTypeLabel } from "@/constants";
import { formatDate } from "@/utils/date";
import { pricePrecision } from "@/utils/pricePrecision";
import type { LedgerTxnRow } from "@/composables/useLedgerTransactions";
import type { useLedgerDetailPage } from "../composables/useLedgerDetailPage";

defineOptions({ name: "LedgerDetailTransactionsPane" });

// #980 P1-C 拆分自 detail.vue：交易记录 Tab 面板（表格 + 分页 + 行操作）。
// txnTypeLabel / formatDate / pricePrecision / LedgerTxnRow 为局部导入，裸用。
const props = defineProps<{ page: ReturnType<typeof useLedgerDetailPage> }>();
const p = reactive(props.page);
</script>

<style scoped>
/* 交易表资产名称列：名称 + 代码 */
.txn-asset-name {
  color: var(--text-primary);
}

.txn-asset-code {
  margin-left: 6px;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}
</style>
