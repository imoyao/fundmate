<template>
  <DrawerSection title="交易记录">
    <template #action>共 {{ transactionsTotal }} 条</template>

    <!-- 加载态：3 行骨架（纯装饰，`aria-hidden` 让读屏只念一次状态即可） -->
    <div v-if="loadingTransactions" class="pt-skeleton" aria-hidden="true">
      <div v-for="row in 3" :key="row" class="pt-skeleton__row" />
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

      <p v-if="transactionsList.length === 0" class="pd-hint pt-empty">
        暂无交易记录
      </p>
    </template>

    <!-- 行内编辑弹窗 -->
    <TransactionEditDialog
      v-model="editDialogVisible"
      :transaction="editingTxn"
      :asset-type="assetType"
      :symbol="symbol"
      @saved="handleSaved"
    />
  </DrawerSection>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getPositionTransactions } from "@/api/positions";
import DrawerSection from "@/components/ProductDrawer/DrawerSection.vue";
import TransactionTable from "@/components/TransactionTable/index.vue";
import type { TransactionRow } from "@/components/TransactionTable/model";
import TransactionEditDialog from "./TransactionEditDialog.vue";

/**
 * 持仓抽屉的交易明细列表（#980 拆分自 `PositionTransactionsDrawer.vue`）。
 *
 * 抽屉是 `destroy-on-close` 的，所以「每次打开重取、关闭即重置」由挂载/销毁天然满足，
 * 不需要父级的 `watch(visible)` + `resetState()` 组合。
 *
 * 设计变更（§6.1 / §6.2）：「共 N 条」从独立一行并进区块标题右侧；
 * 「已加载全部交易记录」删除（运行时自证不是内容）；加载态从一行文案换成 3 行骨架，
 * 免得表格出现前抽屉高度先塌再弹。
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
    // 根据后端实际返回格式解析（分页信封 / 裸数组两种都在线上出现过，
    // 故这里按 unknown 收窄，不用 any）
    const data: unknown = res?.data;

    if (data && typeof data === "object" && "items" in data) {
      const page = data as { items?: unknown; total?: unknown };
      transactionsList.value = Array.isArray(page.items) ? page.items : [];
      transactionsTotal.value = typeof page.total === "number" ? page.total : 0;
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

<style scoped lang="scss">
/* 加载骨架：3 行等宽假表格行，纯装饰 */
.pt-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.pt-skeleton__row {
  height: var(--space-loose);
  background: var(--bg-soft);
  border-radius: var(--radius-sm);
}

.pt-empty {
  margin-top: var(--space-3);
  text-align: center;
}
</style>
