import { ref, type Ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getLedgerTransactions } from "@/api/ledger";
import { deleteTransaction } from "@/api/transaction";
import type { LedgerDetailApi } from "./useLedgerDetail";

/** 交易行（GET /api/ledgers/{id}/transactions/ 分页 items） */
export interface LedgerTxnRow {
  id: number;
  confirm_date?: string | null;
  trade_date?: string | null;
  asset_type?: string | null;
  ledger_id?: number;
  position_name?: string;
  symbol?: string;
  txn_type: string;
  price?: number;
  quantity?: number;
  amount?: number;
  fee?: number;
  notes?: string | null;
}

export interface LedgerTransactionsApi {
  transactionsSearch: Ref<string>;
  transactionsPage: Ref<number>;
  transactionsPageSize: number;
  transactionsList: Ref<LedgerTxnRow[]>;
  transactionsTotal: Ref<number>;
  loadTransactions: (page?: number) => Promise<void>;
  editTxnDialogVisible: Ref<boolean>;
  editingTxn: Ref<LedgerTxnRow | null>;
  openEditTxnDialog: (row: LedgerTxnRow) => void;
  onTxnSaved: () => void;
  confirmDeleteTxn: (row: LedgerTxnRow) => Promise<void>;
  getTxnTypeClass: (type: string) => string;
  resetCache: () => void;
}

/**
 * 交易流水 Tab 的数据加载、搜索、分页、筛选相关状态与函数。
 * 共享状态（ledgerId / holdingsList / loadHoldings）由 useLedgerDetail 持有并传入，
 * 避免重复声明导致状态分裂；交易列表自身状态在此 composable 内私有。
 */
export function useLedgerTransactions(
  detail: LedgerDetailApi
): LedgerTransactionsApi {
  const transactionsPage = ref(1);
  const transactionsPageSize = 20;
  const transactionsList = ref<LedgerTxnRow[]>([]);
  const transactionsTotal = ref(0);
  const transactionsSearch = ref("");

  // 交易编辑（复用持仓明细抽屉同款弹窗）
  const editTxnDialogVisible = ref(false);
  const editingTxn = ref<LedgerTxnRow | null>(null);

  // 交易记录加载
  async function loadTransactions(page = 1) {
    transactionsPage.value = page;
    try {
      const res = await getLedgerTransactions(Number(detail.ledgerId.value), {
        page,
        per_page: transactionsPageSize,
        search: transactionsSearch.value.trim() || undefined
      });
      const result = (
        res as { data?: { items?: LedgerTxnRow[]; total?: number } }
      )?.data;
      transactionsList.value = result?.items ?? [];
      transactionsTotal.value = result?.total ?? 0;
    } catch {
      ElMessage.error("交易记录加载失败");
    }
  }

  function openEditTxnDialog(row: LedgerTxnRow) {
    editingTxn.value = { ...row, ledger_id: Number(detail.ledgerId.value) };
    editTxnDialogVisible.value = true;
  }

  function onTxnSaved() {
    editTxnDialogVisible.value = false;
    loadTransactions(transactionsPage.value);
  }

  // 🔥 修复：确认删除交易
  async function confirmDeleteTxn(row: LedgerTxnRow) {
    // 1. 查找这笔交易对应的持仓对象
    const targetPos = detail.holdingsList.value.find(
      p => p.symbol === row.symbol
    );

    // 2. 如果找到了关联持仓，做防呆处理
    if (targetPos) {
      try {
        await ElMessageBox.confirm(
          `确定要删除这笔交易记录吗？<br/><br/>
          <span style="color: var(--color-warning); font-weight: bold;">重要提示</span><br/>
          当前持仓「${targetPos.name || targetPos.symbol}」共持有 ${targetPos.quantity} 份/股。<br/>
          如果删除这笔历史交易，<b style="color: var(--color-danger-system);">该持仓将丢失成本来源，变成“幽灵持仓”</b>。<br/><br/>
          <b>推荐操作：前往「持仓明细」Tab，找到该持仓并点击“删除”，选择“删除持仓及交易”。</b>`,
          "删除交易风险确认",
          {
            confirmButtonText: "我理解风险，只删除交易",
            cancelButtonText: "取消，我去持仓页操作",
            dangerouslyUseHTMLString: true,
            type: "warning"
          }
        );
        // 用户执意只删交易
        await deleteTransaction(row.id);
        ElMessage.warning("交易记录已删除（持仓已变成幽灵数据）");
        loadTransactions(transactionsPage.value);
        detail.loadHoldings(); // 更新持仓成本
      } catch (e: unknown) {
        if (e !== "cancel") {
          const err = e as { response?: { data?: { message?: string } } };
          ElMessage.error(err?.response?.data?.message || "删除失败");
        }
      }
    } else {
      // 3. 如果找不到对应的持仓（说明本来就是个幽灵交易），直接删
      await deleteTransaction(row.id);
      ElMessage.success("孤立交易已删除");
      loadTransactions(transactionsPage.value);
      detail.loadHoldings();
    }
  }

  // 涨红跌绿：买入/存入=红（rise），卖出/取出=绿（fall），分红等中性=info
  function getTxnTypeClass(type: string) {
    if (type === "buy" || type === "deposit") return "text-[var(--color-rise)]";
    if (type === "sell" || type === "withdraw")
      return "text-[var(--color-fall)]";
    return "text-[var(--color-info)]";
  }

  /** 清空交易列表缓存（删除持仓 / 迁移提交后调用，保证切换 Tab 自动拉取最新数据） */
  function resetCache() {
    transactionsList.value = [];
    transactionsTotal.value = 0;
  }

  const api: LedgerTransactionsApi = {
    transactionsSearch,
    transactionsPage,
    transactionsPageSize,
    transactionsList,
    transactionsTotal,
    loadTransactions,
    editTxnDialogVisible,
    editingTxn,
    openEditTxnDialog,
    onTxnSaved,
    confirmDeleteTxn,
    getTxnTypeClass,
    resetCache
  };

  // 反向绑定：让 useLedgerDetail 的搜索 / 全局刷新 / 删除持仓可触发交易列表刷新或清缓存
  detail.bindTransactions(api);

  return api;
}
