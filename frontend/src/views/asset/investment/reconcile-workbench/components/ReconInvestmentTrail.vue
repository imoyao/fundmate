<template>
  <!--
    抽屉第 ② 段「投资轨迹」。
    owner 原话：「首先要看到这个产品的投资轨迹，或者买卖记录，这样才知道缺了哪些内容」；
    后续补充：记错的流水要在**这一段**直接改（编辑 / 删除），而不是去新增一条。
    数据源走已统一的 TransactionTable（#2104，产品详情 / 账本 Tab / 持仓抽屉共用），
    容器各自取数：有账本按账本 + 代码查，没账本按代码查，并明确显示「未归账本」。
  -->
  <section class="recon-trail">
    <div class="recon-trail__head">
      <div>
        <h3 class="recon-trail__title">这个产品的投资轨迹</h3>
        <p class="recon-trail__hint">
          账本：{{ ledgerName }} · 最近 {{ rows.length }} 笔交易
        </p>
      </div>
      <el-button size="small" text @click="load">刷新流水</el-button>
    </div>

    <div v-if="loading" class="recon-trail__loading" role="status">
      正在读取交易流水…
    </div>

    <SoftBanner v-else-if="error" variant="warning" icon="ep:warning">
      {{ error }}
      <template #actions>
        <el-button size="small" @click="load">重新加载</el-button>
      </template>
    </SoftBanner>

    <template v-else-if="rows.length">
      <TransactionTable
        :rows="rows"
        mode="compact"
        show-account
        show-fee
        show-edit
        show-delete
        :edit-disabled-reason="editDisabledReason"
        table-id="recon-investment-trail"
        :max-height="260"
        @edit="openEdit"
        @delete="onDelete"
      />
      <p class="recon-trail__tip">
        流水记错了可以直接编辑或删除，改完抽屉上方的数字会重新对账。更完整的记录在产品详情页与该账本详情页里。
      </p>
    </template>

    <div v-else class="recon-trail__empty">
      <p>{{ emptyHint }}</p>
      <el-button size="small" @click="goImport">前往交易导入</el-button>
    </div>

    <!-- 行内编辑弹窗：复用账本抽屉的唯一实现，禁止另写一份编辑表单 -->
    <TransactionEditDialog
      v-model="editVisible"
      :transaction="editingTxn"
      :asset-type="editingAssetType"
      :symbol="symbol ?? undefined"
      @saved="handleSaved"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import SoftBanner from "@/components/SoftBanner/index.vue";
import TransactionTable from "@/components/TransactionTable/index.vue";
import type { TransactionRow } from "@/components/TransactionTable/model";
import { getLedgerTransactions } from "@/api/ledger";
import { getTransactions } from "@/api/transactions";
import { deleteTransaction } from "@/api/transaction";
import { errorMessageOf } from "@/utils/errorMessage";
import { transactionDeleteConfirmText } from "@/utils/transactionDeleteConfirm";
import type { TxnRecordLike } from "@/views/asset/ledgers/components/transactionEdit/transactionEditModel";
import TransactionEditDialog from "@/views/asset/ledgers/components/TransactionEditDialog.vue";
import { useReconLedger } from "../composables/useReconLedger";
import { trailEditBlockReason } from "../utils/reconDrawer";

defineOptions({ name: "ReconInvestmentTrail" });

const props = defineProps<{
  symbol: string | null;
  ledgerId: number | null;
  /** 产品名（删除确认文案里点明是哪只，避免删错）；头部已展示，代码兜底 */
  productName?: string | null;
}>();

/** 改完 / 删完通知外层：持仓已按剩余流水重算，差异卡与队列卡都过期了 */
const emit = defineEmits<{ changed: [] }>();

const router = useRouter();
const { ensure, nameOf } = useReconLedger();
const rows = ref<TransactionRow[]>([]);
const loading = ref(false);
const error = ref("");

const ledgerName = computed(() => nameOf(props.ledgerId));
const emptyHint = computed(() =>
  props.ledgerId === null
    ? "这个产品还没有归属账本，账本详情页里也查不到它。先归置账本，或从交易导入补上流水。"
    : "这个账本里还没有该产品的交易流水。缺的很可能就是这一笔，先去交易导入补上。"
);

/** 后端行字段名是 txn_type，公共表格统一收 type（#2104 的唯一分歧） */
function toRows(raw: unknown[]): TransactionRow[] {
  return raw.map((r, index) => {
    const row = (r ?? {}) as Record<string, unknown>;
    return {
      ...row,
      id: Number(row.id ?? index + 1),
      type: String(row.txn_type ?? row.type ?? "other")
    } as TransactionRow;
  });
}

/** 两种信封都兼容：{data:[...]} / {data:{items:[...]}}，取不到就当空态 */
function extract(raw: unknown): unknown[] {
  const payload = (raw as Record<string, unknown>) ?? {};
  const data = (payload.data ?? payload) as unknown;
  if (Array.isArray(data)) return data;
  const wrapped = (data ?? {}) as Record<string, unknown>;
  const list = wrapped.items ?? wrapped.list ?? wrapped.rows;
  return Array.isArray(list) ? list : [];
}

async function load(): Promise<void> {
  if (!props.symbol) {
    rows.value = [];
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const raw = props.ledgerId
      ? await getLedgerTransactions(props.ledgerId, {
          page: 1,
          per_page: 50,
          search: props.symbol
        })
      : await getTransactions({ symbol: props.symbol, per_page: 50 });
    rows.value = toRows(extract(raw));
  } catch {
    // 流水取不到不该拖垮整个抽屉：给一句人话 + 重试，下面的处理动作照常可用
    rows.value = [];
    error.value = "交易流水暂时没加载出来，可以重试，也可以去账本详情页对照。";
  } finally {
    loading.value = false;
  }
}

function goImport(): void {
  void router.push("/inventory/investment/import");
}

/* ── 行内编辑 / 删除 ──────────────────────────────────────────────
 * 编辑弹窗复用 TransactionEditDialog（唯一实现）；删除确认文案走
 * utils/transactionDeleteConfirm（与持仓抽屉共用，不许再写第二份）。 */

const editVisible = ref(false);
const editingTxn = ref<TxnRecordLike | null>(null);
const editingAssetType = computed(
  () => editingTxn.value?.asset_type ?? undefined
);

/** 未归属账本的行编辑置灰（后端 PATCH 只接受已归账本的流水）；删除照常可用 */
function editDisabledReason(row: TransactionRow): string {
  return trailEditBlockReason(row);
}

function openEdit(row: unknown): void {
  editingTxn.value = row as TxnRecordLike;
  editVisible.value = true;
}

function handleSaved(data: TxnRecordLike): void {
  const updated = (data ?? {}) as Partial<TransactionRow>;
  const idx = rows.value.findIndex(t => t.id === updated.id);
  if (idx !== -1) {
    Object.assign(rows.value[idx], updated);
  }
  // 数量 / 价格同样会改份额与成本：抽屉上方数字与队列卡过期
  emit("changed");
}

/** 删除单笔流水：确认文案与控制流沿用持仓抽屉口径（后端按剩余流水重算持仓） */
async function onDelete(row: unknown): Promise<void> {
  const txn = row as TransactionRow;
  if (txn.id == null) return;

  const label = props.productName || props.symbol || "该产品";
  try {
    await ElMessageBox.confirm(
      transactionDeleteConfirmText(label),
      "删除这笔交易？",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
    );
  } catch {
    return; // 用户取消
  }

  try {
    await deleteTransaction(txn.id);
    ElMessage.success("交易已删除，持仓已重算");
    await load();
    emit("changed");
  } catch (e) {
    ElMessage.error(errorMessageOf(e) || "删除失败");
  }
}

onMounted(() => {
  void ensure();
});

watch(
  () => [props.symbol, props.ledgerId],
  () => {
    void load();
  },
  { immediate: true }
);
</script>

<style scoped>
.recon-trail {
  padding: var(--space-standard);
  margin-bottom: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}

.recon-trail__head {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 10px;
}

.recon-trail__title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.recon-trail__hint {
  margin: 4px 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.recon-trail__loading,
.recon-trail__empty {
  padding: var(--space-standard);
  font-size: var(--text-small);
  color: var(--text-secondary);
  text-align: center;
}

.recon-trail__empty p {
  margin: 0 0 10px;
  line-height: 1.7;
}

.recon-trail__tip {
  margin: 10px 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}
</style>
