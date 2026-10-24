// frontend/src/views/asset/investment/manual/conversion/useConversionPositions.ts
// 转换页的持仓来源（#980 拆分自 ConversionForm.vue）。
//
// 与卖出表单同源（`getPositionsGroupedByAccount` 一次拉全账户再按账本过滤），
// 差别只有一处：**只认基金持仓**——货基 / 逆回购没有费率阶梯语义，
// 后端也不支持它们做转换，前端先滤掉以免用户选了才被拒。

import { computed, ref, type ComputedRef } from "vue";
import { getPositionsGroupedByAccount } from "@/api/positions";
import type { Position } from "@/api/types";
import type { ConversionFormModel } from "./conversionFormModel";

export function useConversionPositions(
  form: ConversionFormModel,
  ledgerId: ComputedRef<number | null>,
  /** 拉完持仓后把「有基金持仓的账本 ID」回抛给父页（父页据此过滤账户下拉） */
  onPositionsLoaded: (ledgerIds: number[]) => void
) {
  const positionsByAccount = ref<Record<string, Position[]>>({});
  const loadingPositions = ref(false);

  /** 当前账户的**基金**持仓 */
  const accountPositions = computed<Position[]>(() => {
    const all: Position[] = [];
    for (const list of Object.values(positionsByAccount.value)) {
      all.push(...list);
    }
    return all.filter(p => p.ledger_id === ledgerId.value && p.type === "fund");
  });

  const selectedPosition = computed(
    () => accountPositions.value.find(p => p.id === form.positionId) || null
  );

  /** 转出份额上限（持仓精确值） */
  const maxQuantity = computed(() =>
    Number(selectedPosition.value?.quantity ?? 0)
  );

  async function loadPositions() {
    loadingPositions.value = true;
    try {
      const res = await getPositionsGroupedByAccount();
      const data = (res?.data ?? {}) as Record<string, Position[]>;
      positionsByAccount.value = data;
      const ledgerIds = new Set<number>();
      for (const list of Object.values(data)) {
        for (const p of list) {
          if (p.type === "fund" && p.ledger_id != null) {
            ledgerIds.add(p.ledger_id);
          }
        }
      }
      onPositionsLoaded([...ledgerIds]);
    } catch {
      positionsByAccount.value = {};
    } finally {
      loadingPositions.value = false;
    }
  }

  return {
    positionsByAccount,
    loadingPositions,
    accountPositions,
    selectedPosition,
    maxQuantity,
    loadPositions
  };
}
