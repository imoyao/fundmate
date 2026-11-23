/**
 * 账户详情页「近 90 天区间收益 vs 基准」数据源（#2134 → #3222 下沉）。
 *
 * 从 `LedgerDetailOverview.vue` 下沉：那页受页面规模门禁（400 行，只减不增）
 * 约束，而这段「取超额收益 + 派生四个降级字段」是纯读、无副作用，放页面里
 * 只会把它顶破阈值（同 `overviewMetrics` / `useLedgerSections` 的拆分理由）。
 *
 * 口径：缺数据诚实降级 null → 模板显示「--」，概览区不因超额计算失败而打断。
 */
import { computed, ref, watch } from "vue";
import type { ComputedRef, Ref } from "vue";
import { getBenchmarkExcess, type BenchmarkExcessResult } from "@/api/summary";
import { excessDateRange, excessDegradHint } from "@/utils/benchmarkExcess";

export interface BenchmarkExcessApi {
  rangeRate: ComputedRef<number | null>;
  benchReturn: ComputedRef<number | null>;
  excessReturn: ComputedRef<number | null>;
  excessHint: ComputedRef<string | null>;
}

/**
 * @param ledgerIdNum 有限数字账户 id（无 id 时不取，避免打到家庭档）。
 * @param ledgerId 路由原始 id（watch 源：切账户时重取）。
 */
export function useBenchmarkExcess(
  ledgerIdNum: Ref<number | undefined>,
  ledgerId: Ref<string>
): BenchmarkExcessApi {
  const excess = ref<BenchmarkExcessResult | null>(null);

  const rangeRate = computed(() => excess.value?.range_rate ?? null);
  const benchReturn = computed(
    () => excess.value?.benchmark?.range_return ?? null
  );
  const excessReturn = computed(() => excess.value?.excess_return ?? null);
  const excessHint = computed(() => excessDegradHint(excess.value));

  async function fetchExcess() {
    const id = ledgerIdNum.value;
    if (!id) {
      excess.value = null;
      return;
    }
    try {
      const res = await getBenchmarkExcess({
        ...excessDateRange(),
        ledger_id: id
      });
      excess.value = res.data;
    } catch {
      excess.value = null;
    }
  }

  watch(ledgerId, () => void fetchExcess(), { immediate: true });

  return { rangeRate, benchReturn, excessReturn, excessHint };
}
