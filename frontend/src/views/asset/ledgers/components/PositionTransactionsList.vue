<template>
  <div class="flex-1 overflow-y-auto">
    <div class="flex justify-between items-center mb-3">
      <span
        class="text-sm font-medium"
        :style="{ color: 'var(--text-secondary)' }"
        >交易记录</span
      >
      <span class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }"
        >共 {{ transactionsTotal }} 条</span
      >
    </div>

    <!-- 加载状态 -->
    <div
      v-if="loadingTransactions"
      class="text-center py-8"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      <el-icon class="is-loading" :size="20"><Loading /></el-icon>
      <p class="mt-2 text-xs">加载交易记录中...</p>
    </div>

    <template v-else>
      <!-- 表格本体走全站统一的 TransactionTable（#2104 验收「同一组件」）。
           抽屉单持仓视图：无产品列（抽屉头部已显示持仓名）、无账户列，
           基金品类走「确认净值/确认份额」标签（fund 确认语义）。 -->
      <TransactionTable
        :rows="rows"
        mode="compact"
        show-fee
        show-edit
        :price-label="isFund ? '确认净值' : '单价'"
        :quantity-label="isFund ? '确认份额' : '数量'"
        @edit="openEdit"
      />

      <!-- 🔥 修复3：明确加载完成的提示 -->
      <div
        v-if="!loadingTransactions && transactionsList.length > 0"
        class="text-center text-xs mt-4 pb-2"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        已加载全部交易记录
      </div>

      <div
        v-if="transactionsList.length === 0"
        class="text-center py-6 text-xs"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        暂无交易记录
      </div>
    </template>

    <!-- 行内编辑弹窗 -->
    <TransactionEditDialog
      v-model="editDialogVisible"
      :transaction="editingTxn"
      :asset-type="assetType"
      :symbol="symbol"
      @saved="handleSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Loading } from "@element-plus/icons-vue";
import { getPositionTransactions } from "@/api/positions";
import TransactionTable, {
  type TransactionRow
} from "@/components/TransactionTable/index.vue";
import TransactionEditDialog from "./TransactionEditDialog.vue";

/**
 * 持仓抽屉的交易明细列表（#980 拆分自 `PositionTransactionsDrawer.vue`）。
 *
 * 抽屉是 `destroy-on-close` 的，所以「每次打开重取、关闭即重置」由挂载/销毁天然满足，
 * 不再需要父级那个 `watch(visible)` + `resetState()` 的组合。
 */
defineOptions({ name: "PositionTransactionsList" });

const props = withDefaults(
  defineProps<{
    positionId?: number | string | null;
    assetType?: string | null;
    symbol?: string | null;
    /** 基金品类：表头用「确认净值 / 确认份额」 */
    isFund?: boolean;
  }>(),
  { positionId: null, assetType: null, symbol: null, isFund: false }
);

// 交易记录状态
const loadingTransactions = ref(false);
const transactionsList = ref<any[]>([]);
const transactionsTotal = ref(0);

/** 适配公共表格行：txn_type → type（spread 保留原字段，编辑弹窗所需的
    notes / import_hash 运行时仍在，仅类型层面不收）。 */
const rows = computed<TransactionRow[]>(() =>
  transactionsList.value.map(r => ({ ...r, type: r.txn_type }))
);

// 获取交易明细 API 调用
async function fetchTransactions() {
  if (!props.positionId) return;

  loadingTransactions.value = true;
  try {
    const res = await getPositionTransactions(props.positionId as number);
    // 根据后端实际返回格式解析
    const data = (res as any)?.data;

    // 兼容处理
    if (data && typeof data === "object" && "items" in data) {
      transactionsList.value = data.items || [];
      transactionsTotal.value = data.total || 0;
    } else {
      transactionsList.value = Array.isArray(data) ? data : [];
      transactionsTotal.value = transactionsList.value.length;
    }
  } catch {
    transactionsList.value = [];
    transactionsTotal.value = 0;
  } finally {
    loadingTransactions.value = false;
  }
}

// 行内编辑
const editDialogVisible = ref(false);
const editingTxn = ref<any>(null);

function openEdit(row: any) {
  editingTxn.value = row;
  editDialogVisible.value = true;
}

function handleSaved(data: any) {
  const idx = transactionsList.value.findIndex(t => t.id === data?.id);
  if (idx !== -1) {
    Object.assign(transactionsList.value[idx], {
      quantity: data.quantity,
      price: data.price,
      amount: data.amount,
      fee: data.fee,
      trade_date: data.trade_date || data.confirm_date || null,
      confirm_date: data.confirm_date,
      notes: data.notes,
      import_hash: data.import_hash
    });
  }
}

onMounted(() => fetchTransactions());
</script>
