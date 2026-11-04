import { computed, ref, type Ref } from "vue";
import { getPositionsGroupedByAccount } from "@/api/positions";
import type { Position } from "@/api/types";
import { getStep } from "@/utils/trading";

interface SellPositionsForm {
  ledger_id: number | null;
  positionId: number | null;
  symbol: string;
  market: string;
  type: string;
  price: number | undefined;
  quantity: number | undefined;
  fee: number | undefined;
}

/**
 * 卖出表单的「账户 → 持仓 → 可卖量 / 步长 / 快捷档位」链路（#980 从 SellForm 拆出）。
 *
 * 关键口径（都在这条链上，别再散回模板里算）：
 * - 账户可用性：只列「有持仓」的账户，分组键是 ledger_id（后端 group_by=account 按真
 *   外键分组，#2372/#2405）——账户名可编辑且真库有重名，按名回查会落空或串账户；
 * - 可卖量 maxQuantity 取持仓 quantity；步长按品类/市场走 utils/trading.getStep；
 * - 碎股（持仓 < 一手）允许全部卖出，故 sellMin 取 min(持仓, 步长)；
 * - 预估金额 = 数量 × 价格 − 手续费，非正数显示 "-"。
 */
export function useSellPositions(deps: {
  /** 账户列表（父组件 props.ledgers，取函数以免解构丢响应性） */
  getLedgers: () => any[];
  form: SellPositionsForm;
  selectedPosition: Ref<any>;
  /** 持仓加载完把涉及的 ledger_id 广播给父组件（页面据此预取） */
  onLoaded?: (ledgerIds: number[]) => void;
}) {
  const { form, selectedPosition } = deps;
  const positionsByAccount = ref<Record<string, Position[]>>({});
  const qtyTouched = ref(false);

  const availableAccounts = computed(() =>
    deps
      .getLedgers()
      .filter(l => positionsByAccount.value[String(l.id)]?.length > 0)
  );
  const currentLedger = computed(
    () => deps.getLedgers().find(l => l.id === form.ledger_id) ?? null
  );
  const accountPositions = computed(() => {
    if (!currentLedger.value) return [];
    return positionsByAccount.value[String(currentLedger.value.id)] || [];
  });
  const maxQuantity = computed(() => selectedPosition.value?.quantity ?? 1);
  const stepForSecurity = computed(() => {
    if (!selectedPosition.value) return 1;
    return getStep({
      type: form.type,
      market: form.market,
      symbol: form.symbol
    });
  });
  const sellMin = computed(() => {
    const total = maxQuantity.value;
    if (form.type === "fund") return total > 0 ? 0.0001 : 0;
    return total < stepForSecurity.value ? total : stepForSecurity.value;
  });
  const placeholderText = computed(() => {
    const total = maxQuantity.value;
    const unit =
      form.type === "fund" ? " 份" : form.type === "bond" ? " 张" : " 股/张";
    return `最多可卖出 ${total}${unit}`;
  });
  const isOddLot = computed(() => {
    const total = maxQuantity.value;
    return total > 0 && total < stepForSecurity.value;
  });
  const showQtyHint = computed(() => {
    if (!qtyTouched.value) return false;
    const q = form.quantity;
    if (q == null) return true;
    return q < sellMin.value;
  });
  const sellEstimate = computed(() => {
    const q = form.quantity || 0;
    const p = form.price || 0;
    const f = form.fee || 0;
    const amount = q * p - f;
    return amount > 0 ? amount.toFixed(2) : "-";
  });
  const showIsAfter15 = computed(() => {
    const type = currentLedger.value?.ledger_type;
    if (type === "fund" || type === "bank") return true;
    if (type === "stock" && selectedPosition.value?.type === "fund")
      return true;
    return false;
  });

  async function fetchPositionsByAccount() {
    try {
      const res = await getPositionsGroupedByAccount();
      positionsByAccount.value = res?.data ?? {};
      const ids = new Set<number>();
      // #2405：分组键是 ledger_id 字符串（重名账户各成一组），不是账户名
      for (const ledgerKey in positionsByAccount.value) {
        const positions = positionsByAccount.value[ledgerKey];
        positions.forEach(p => {
          if (p.ledger_id) ids.add(p.ledger_id);
        });
      }
      deps.onLoaded?.(Array.from(ids));
    } catch {
      positionsByAccount.value = {};
      deps.onLoaded?.([]);
    }
  }

  /** 表单重置时清空持仓缓存（避免残留上一个账户的持仓） */
  function resetPositions() {
    positionsByAccount.value = {};
  }

  return {
    positionsByAccount,
    qtyTouched,
    availableAccounts,
    currentLedger,
    accountPositions,
    maxQuantity,
    stepForSecurity,
    sellMin,
    placeholderText,
    isOddLot,
    showQtyHint,
    sellEstimate,
    showIsAfter15,
    fetchPositionsByAccount,
    resetPositions
  };
}
