import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import {
  getLedgerConsistency,
  type LedgerConsistencyItem
} from "@/api/reconciliation";
import { useLedgerDetail } from "@/composables/useLedgerDetail";
import { useLedgerTransactions } from "@/composables/useLedgerTransactions";
import { usePositionMigration } from "@/composables/usePositionMigration";

/**
 * 账户详情页状态单体（#980 P1-C 纯结构拆分）：
 * 组合既有三个领域 composable（useLedgerDetail / useLedgerTransactions /
 * usePositionMigration）与页面级「温柔提醒」持仓快照一致性状态（#1133 §4），
 * 平铺返回——detail（42 成员）与 txns（11 成员）键集不相交，展开无覆盖。
 * 页面壳 index.vue 与三个子组件经同一 page 实例共享状态。
 */
export function useLedgerDetailPage() {
  const router = useRouter();

  const detail = useLedgerDetail();
  const txns = useLedgerTransactions(detail);
  const migration = usePositionMigration(detail);
  const { ledgerId } = detail;
  const { handleAssign } = migration;

  // ── 温柔提醒（#1133 §4）：账户持仓快照一致性，中性、非阻断 ──
  const consistencyItems = ref<LedgerConsistencyItem[]>([]);
  const DISMISS_KEY = "fundmate:soft-recon-dismiss";
  function loadDismissed(): Set<string> {
    try {
      const raw = localStorage.getItem(DISMISS_KEY);
      if (raw) {
        const arr = JSON.parse(raw);
        if (Array.isArray(arr)) return new Set(arr as string[]);
      }
    } catch {
      /* 忽略损坏的本地存储 */
    }
    return new Set();
  }
  function saveDismissed(set: Set<string>) {
    try {
      localStorage.setItem(DISMISS_KEY, JSON.stringify([...set]));
    } catch {
      /* 忽略写入失败（隐私模式等） */
    }
  }
  const dismissedKeys = ref<Set<string>>(loadDismissed());

  const visibleConsistencyItems = computed(() =>
    consistencyItems.value
      .filter(
        it => it.ledger_id != null && String(it.ledger_id) === ledgerId.value
      )
      .filter(
        it =>
          !dismissedKeys.value.has(
            `${it.ledger_id}:${it.symbol}:${it.snapshot_date}`
          )
      )
  );

  async function loadConsistency() {
    try {
      const res = await getLedgerConsistency(
        ledgerId.value ? Number(ledgerId.value) : undefined
      );
      consistencyItems.value = res.data?.items ?? [];
    } catch {
      consistencyItems.value = [];
    }
  }
  function dismissAllConsistency() {
    const next = new Set(dismissedKeys.value);
    for (const it of visibleConsistencyItems.value) {
      next.add(`${it.ledger_id}:${it.symbol}:${it.snapshot_date}`);
    }
    dismissedKeys.value = next;
    saveDismissed(next);
  }
  function goReconcile() {
    router.push({ name: "ReconcileWorkbench" });
  }

  onMounted(() => {
    loadConsistency();
  });

  return {
    ...detail,
    ...txns,
    handleAssign,
    visibleConsistencyItems,
    dismissAllConsistency,
    goReconcile,
    router
  };
}
