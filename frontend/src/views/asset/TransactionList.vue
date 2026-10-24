<script setup lang="ts">
// 交易流水列表：状态与取数留在这一层，渲染与滚动细节交给三个子组件。
//
// 子组件分工：TransactionToolbar（筛选 + 视图开关）、TransactionTableView（表格 + 分页）、
// TransactionTimelineView（按日折叠 + 触底加载）。纯展示口径集中在 transactionListModel.ts。
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { getTransactions, exportTransactions } from "@/api/transactions";
import type { TransactionRecord } from "@/api/transactions";
import { ElMessage } from "element-plus";
import TransactionEditDialog from "./ledgers/components/TransactionEditDialog.vue";
import TransactionToolbar from "./transactionList/TransactionToolbar.vue";
import TransactionTableView from "./transactionList/TransactionTableView.vue";
import TransactionTimelineView from "./transactionList/TransactionTimelineView.vue";
import {
  buildTransactionParams,
  defaultFilters,
  type TransactionFilters
} from "./transactionList/transactionListModel";

defineOptions({ name: "TransactionList" });

const viewMode = ref("table");
const transactions = ref<TransactionRecord[]>([]);
const loading = ref(false);
const loadingMore = ref(false);
const hasMore = ref(true);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(10);
const filters = ref<TransactionFilters>(defaultFilters());

const route = useRoute();
const router = useRouter();

/**
 * 从 query 初始化 symbol 筛选。
 * 用 `String()` 收敛：query 值类型是 `string | string[] | null`，重复 query
 * （`?symbol=a&symbol=b`）会拿到数组，直接赋值会让 params.symbol 变数组并被
 * axios 序列化成 `symbol[]=a&symbol[]=b`——后端 `request.args.get('symbol')`
 * 只取到第一个，静默筛错且没有任何报错。
 */
function applySymbolFromQuery() {
  const raw = route.query.symbol;
  const picked = Array.isArray(raw) ? raw[0] : raw;
  filters.value.symbol = picked ? String(picked) : "";
}

async function fetchData(isLoadMore = false) {
  if (loading.value || loadingMore.value) return;
  if (isLoadMore) loadingMore.value = true;
  else loading.value = true;

  try {
    const res = await getTransactions(
      buildTransactionParams(filters.value, currentPage.value, pageSize.value)
    );
    const newData = res?.data ?? [];
    transactions.value = isLoadMore
      ? [...transactions.value, ...newData]
      : newData;
    total.value = res?.total ?? 0;
    hasMore.value = transactions.value.length < total.value;
  } catch (e: any) {
    ElMessage.error(e?.message || "加载流水失败");
  } finally {
    loading.value = false;
    loadingMore.value = false;
  }
}

// 重置刷新
const resetAndFetch = () => {
  currentPage.value = 1;
  hasMore.value = true;
  fetchData();
};

/**
 * 筛选项变化。原实现把 `fetchData` 直接挂在 `@change` 上，Element Plus 会把
 * 新值当第一个参数传进去，于是 `isLoadMore` 收到 `"buy"` 这种真值——变成
 * 追加模式（旧筛选的结果留在列表里）且页码不重置。这里显式忽略载荷走重置刷新。
 */
const onFilterChange = () => {
  resetAndFetch();
};

// 时间线触底加载下一页
const onLoadMore = () => {
  currentPage.value++;
  fetchData(true);
};

/**
 * 清除 symbol 预筛（#2160）。同时把 query 里的 symbol 摘掉——
 * 只清本地状态的话，刷新页面 query 会把筛选原样带回来，用户清不掉。
 */
function clearSymbolFilter() {
  filters.value.symbol = "";
  // 用 clone + delete 而不是 `const { symbol, ...rest }`——那个解构出的 `symbol`
  // 在本函数里用不到，会撞 `@typescript-eslint/no-unused-vars`
  // （本项目 eslint 配置只开了 args/vars 的 `^_` 前缀豁免，没开 ignoreRestSiblings）。
  const nextQuery = { ...route.query };
  delete nextQuery.symbol;
  void router.replace({ query: nextQuery });
  resetAndFetch();
}

// 行内编辑
const editDialogVisible = ref(false);
const editingTxn = ref<any>(null);
function openEdit(row: any) {
  editingTxn.value = row;
  editDialogVisible.value = true;
}
function handleSaved(data: any) {
  const idx = transactions.value.findIndex(t => t.id === data?.id);
  if (idx !== -1) {
    Object.assign(transactions.value[idx], {
      quantity: data.quantity,
      price: data.price,
      amount: data.amount,
      fee: data.fee,
      trade_date: data.trade_date,
      confirm_date: data.confirm_date,
      notes: data.notes,
      import_hash: data.import_hash
    });
  }
}

// 导出全部交易流水
const exporting = ref(false);
const handleExport = async () => {
  if (exporting.value) return;
  exporting.value = true;
  try {
    await exportTransactions();
  } catch (e: any) {
    ElMessage.error(e?.message || "导出失败");
  } finally {
    exporting.value = false;
  }
};

// 分页
const onPageChange = (page: number) => {
  currentPage.value = page;
  fetchData();
};
const onSizeChange = (size: number) => {
  pageSize.value = size;
  currentPage.value = 1;
  fetchData();
};

onMounted(() => {
  // #2160：先按 query 定筛选再取数，否则会先用「无 symbol」的参数拉一次全量再改
  applySymbolFromQuery();
  fetchData();
});

/**
 * query 变化时重新套用筛选（#2160）。列表页会被 keepAlive 复用：
 * 用户可能已经从详情页跳来过一次、返回后再从别处 push 进来，
 * 只在 onMounted 读一次 query 会出现「URL 变了但筛选没变」。
 */
watch(
  () => route.query.symbol,
  (next, prev) => {
    if (next === prev) return;
    applySymbolFromQuery();
    resetAndFetch();
  }
);
</script>

<template>
  <div class="transaction-list p-4 md:p-6 bg-[#f5f7fa] min-h-full">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h2 class="text-2xl font-bold text-gray-800">交易流水</h2>
      <p class="text-gray-500 mt-1 text-sm">所有交易操作的历史记录</p>
    </div>

    <TransactionToolbar
      v-model:view-mode="viewMode"
      v-model:filters="filters"
      :total-count="total"
      :loading="loading"
      :exporting="exporting"
      @change="onFilterChange"
      @reset="resetAndFetch"
      @export="handleExport"
      @clear-symbol="clearSymbolFilter"
    />

    <TransactionTableView
      v-if="viewMode === 'table'"
      :transactions="transactions"
      :loading="loading"
      :total="total"
      :current-page="currentPage"
      :page-size="pageSize"
      @page-change="onPageChange"
      @size-change="onSizeChange"
      @edit="openEdit"
    />

    <TransactionTimelineView
      v-if="viewMode === 'timeline'"
      :transactions="transactions"
      :loading="loading"
      :loading-more="loadingMore"
      :has-more="hasMore"
      @edit="openEdit"
      @load-more="onLoadMore"
    />

    <!-- 行内编辑弹窗 -->
    <TransactionEditDialog
      v-model="editDialogVisible"
      :transaction="editingTxn"
      :asset-type="editingTxn?.asset_type"
      :symbol="editingTxn?.symbol"
      @saved="handleSaved"
    />
  </div>
</template>
