<script setup lang="ts">
import { computed, ref } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getTransactions, type TransactionRecord } from "@/api/transactions";
import { formatQuantity } from "@/utils/format";

/**
 * 详情页「交易记录」区块（#2104 · 设计 §4.2）。
 *
 * 数据来自 `GET /api/transactions/?symbol=`，过滤在**后端下推到 SQL**
 * （#2104 新增的 symbol 参数），不在前端拉全量再筛——后者是数据策略硬约束 §6 明令禁止的。
 *
 * 口径：
 * - 按 trade_date 倒序、id 倒序（与后端 `build_transaction_list` 一致）；
 * - 金额/份额基于 money 换算（分 → 元、份 → 份），不直接对 float 做乘除；
 * - 涨跌颜色交给 `MoneyDisplay` 的 autoColor（涨红跌绿语义变量），此处不自己拼颜色。
 */

const props = defineProps<{
  /** 产品代码（后端按 transactions.symbol 字面量快照匹配） */
  symbol: string;
  /** 资产类型（用于判断是否需要展示该区块） */
  assetType: string;
}>()

const loading = ref(false)
const transactions = ref<TransactionRecord[]>([])
const errorMsg = ref<string | null>(null)

const hasTransactions = computed(() => transactions.value.length > 0)

async function loadTransactions() {
  loading.value = true
  errorMsg.value = null
  try {
    const { data } = await getTransactions({
      symbol: props.symbol,
      per_page: 10,
    })
    transactions.value = data.data
  } catch (err) {
    console.error("加载交易记录失败", err)
    errorMsg.value = "加载失败，请稍后重试"
  } finally {
    loading.value = false
  }
}

// 组件挂载时加载
void loadTransactions()

/** 操作类型中文映射 */
const txnTypeLabel: Record<string, string> = {
  buy: "买入",
  sell: "卖出",
  dividend: "分红",
  deposit: "存入",
  withdraw: "取出",
  split: "拆分",
}

function formatTradeDate(date: string | null): string {
  if (!date) return "—"
  return date
}

function formatAmount(amount: number): string {
  if (amount === 0) return "0.00"
  return amount.toFixed(2)
}
</script>

<template>
  <CardBlock>
    <template #header>
      <SectionHeader title="交易记录" />
    </template>

    <div v-if="loading" class="transaction-section__loading">
      <el-skeleton :rows="3" animated />
    </div>

    <div v-else-if="errorMsg" class="transaction-section__error">
      <span>{{ errorMsg }}</span>
    </div>

    <div v-else-if="!hasTransactions" class="transaction-section__empty">
      <span>暂无交易记录</span>
    </div>

    <div v-else class="transaction-section__list">
      <el-table :data="transactions" size="small" border>
        <el-table-column prop="trade_date" label="交易日期" width="100">
          <template #default="{ row }">
            {{ formatTradeDate(row.trade_date) }}
          </template>
        </el-table-column>
        <el-table-column prop="type" label="操作" width="60">
          <template #default="{ row }">
            {{ txnTypeLabel[row.type] || row.type }}
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="100">
          <template #default="{ row }">
            {{ formatQuantity(row.quantity) }}
          </template>
        </el-table-column>
        <el-table-column prop="price" label="价格" width="100">
          <template #default="{ row }">
            <MoneyDisplay :value="row.price" :decimals="2" />
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="100">
          <template #default="{ row }">
            <MoneyDisplay :value="row.amount" :decimals="2" />
          </template>
        </el-table-column>
        <el-table-column prop="account_name" label="账户" min-width="100">
          <template #default="{ row }">
            {{ row.account_name || "未知账户" }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </CardBlock>
</template>

<style scoped>
.transaction-section__loading {
  padding: 16px;
}

.transaction-section__error {
  padding: 16px;
  color: var(--color-fall);
  text-align: center;
}

.transaction-section__empty {
  padding: 24px;
  color: var(--color-text-3);
  text-align: center;
}

.transaction-section__list {
  width: 100%;
}
</style>
