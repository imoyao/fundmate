<script setup lang="ts">
// 交易流水列表：状态与取数留在这一层，渲染与滚动细节交给三个子组件。
//
// 子组件分工：TransactionToolbar（卡头：视图切换 + 一级/二级筛选）、
// TransactionTableView（表格 + 分页 + 行展开详情按需取）、
// TransactionTimelineView（按月分组 + 触底加载）。纯展示口径集中在 transactionListModel.ts。
//
// 页面骨架按 docs/design/transaction-flow-redesign.md §二 的三条横带：
// 页头（我是谁）→ 汇总条（这段时间发生了什么）→ 列表卡（具体哪一笔）。
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Download } from "@element-plus/icons-vue";
import {
  getTransactionSummary,
  getTransactions,
  exportTransactions
} from "@/api/transactions";
import type { TransactionRecord, TransactionSummary } from "@/api/transactions";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import { ElMessage } from "element-plus";
import TransactionEditDialog from "./ledgers/components/TransactionEditDialog.vue";
import TransactionSummaryBar from "./transactionList/TransactionSummaryBar.vue";
import TransactionToolbar from "./transactionList/TransactionToolbar.vue";
import TransactionTableView from "./transactionList/TransactionTableView.vue";
import TransactionTimelineView from "./transactionList/TransactionTimelineView.vue";
import {
  buildFilterParams,
  buildTransactionParams,
  defaultFilters,
  summaryRangeLabel,
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

/** 表格视图的实例：编辑保存后要清它的展开详情缓存（否则展开行还显示改之前的备注） */
const tableViewRef = ref<InstanceType<typeof TransactionTableView> | null>(
  null
);

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

/**
 * 汇总条数据（设计 §四）。它只跟**筛选**走，不跟分页——翻页、触底加载都不该重取：
 * 汇总回答的是「这段时间怎么样」，与当前看到第几页无关。
 *
 * 失败**静默**：列表接口失败已经弹过 toast，汇总再弹一个就是两条噪声；而汇总未取到时
 * 汇总条整块不渲染，页面照常可用。
 */
const summary = ref<TransactionSummary | null>(null);
const summaryLoading = ref(false);
const summaryLabel = computed(() => summaryRangeLabel(filters.value));
/** 请求序号：快速连点筛选时，先发出的慢响应不许覆盖后发的结果（否则数字会对不上筛选） */
let summarySeq = 0;

async function fetchSummary() {
  const seq = ++summarySeq;
  summaryLoading.value = true;
  try {
    const res = await getTransactionSummary(buildFilterParams(filters.value));
    if (seq !== summarySeq) return;
    summary.value = res?.data ?? null;
  } catch {
    // 保持上一次的数字（若已有）；没有就继续不渲染。切筛选失败时不硬造 0。
    if (seq === summarySeq && !summary.value) summary.value = null;
  } finally {
    if (seq === summarySeq) summaryLoading.value = false;
  }
}

// 重置刷新（筛选变化 / 清空筛选 / 清 symbol 都走这里）
const resetAndFetch = () => {
  currentPage.value = 1;
  hasMore.value = true;
  fetchData();
  fetchSummary();
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
  // 展开详情是「取一次就缓存」的：不清掉的话，改完备注再展开那一行仍显示改前的内容。
  tableViewRef.value?.clearDetails();
  // 金额 / 手续费可能被改过，汇总要跟着变——否则改完一笔，上面那行数字还说旧话。
  fetchSummary();
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
  fetchSummary();
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
  <div
    class="transaction-list min-h-full"
    :style="{ background: 'var(--bg-page)' }"
  >
    <!-- 页头：一层就够。此前是 h2 + 副标题，下面再起一张筛选卡——同一屏两个头顶 -->
    <PageHeaderBar
      title="交易流水"
      subtitle="买入、卖出、转入转出的完整记录，按交易日倒序排列"
    >
      <template #action>
        <el-button :icon="Download" :loading="exporting" @click="handleExport">
          导出 CSV
        </el-button>
      </template>
    </PageHeaderBar>

    <div class="transaction-list__shell">
      <!-- 汇总条：跟随筛选，一行读完（设计 §二 第二带）。数据未就绪时自身不渲染，
           所以这里不需要再造一个「加载中」的壳。 -->
      <TransactionSummaryBar
        :summary="summary"
        :label="summaryLabel"
        :loading="summaryLoading"
      />

      <!-- 筛选卡头与列表同处一张卡（设计 §六）。body padding 归零：卡头自带内边距，
           再叠一层 EL 默认的 20px 会让「卡头贴边、列表缩进」两处对不齐。 -->
      <el-card shadow="never" :body-style="{ padding: '0' }">
        <TransactionToolbar
          v-model:view-mode="viewMode"
          v-model:filters="filters"
          :total-count="total"
          :loading="loading"
          @change="onFilterChange"
          @reset="resetAndFetch"
          @clear-symbol="clearSymbolFilter"
        />

        <TransactionTableView
          v-if="viewMode === 'table'"
          ref="tableViewRef"
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
      </el-card>
    </div>

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

<style scoped>
/* 与 PageHeaderBar 的 max-width / 横向内边距对齐（同 dividends 页的 shell 口径） */
.transaction-list__shell {
  max-width: var(--layout-content-width);
  padding: 0 var(--space-standard);
  margin: 0 auto;
}
</style>
