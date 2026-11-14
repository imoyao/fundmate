import { computed, onMounted, ref, watch } from "vue";
import { getCashFlow, type CashFlow } from "@/api/summary";
import { errorMessageOf } from "@/utils/errorMessage";
import { formatAmount } from "@/utils/currency";
import {
  cashFlowParams,
  type CashFlowRange,
  type CashFlowScope
} from "./cashFlowParams";

/**
 * 资金流动的取数与区间状态（从 `index.vue` 抽出）。
 *
 * 抽出的直接理由：`index.vue` 已贴近 vue-size 的 400 行阈值，
 * 把取数收敛到 composable 后主文件净减。
 * 另一层理由：区间枚举与请求参数以前埋在组件里，全周期口径无法单测，
 * 现在收敛到无依赖的 `cashFlowParams.ts` 纯函数并配单测。
 *
 * 档位表本身在 `utils/chartRange.ts`（#3109 与超额走势 / 收益归因共用）；
 * `inception` 由后端按作用域解析最早资金流水，前端无需先取 first_txn_date
 * 再发第二次请求（冷启动鸡生蛋）。
 */
export type { CashFlowScope };

export function useCashFlow(scope: CashFlowScope) {
  /** 默认近1年：与改造前的 365 天等价，切档带来的口径变化不该由默认值承担 */
  const range = ref<CashFlowRange>("1y");
  const data = ref<CashFlow | null>(null);
  const loadError = ref("");

  const totals = computed(() => data.value?.totals ?? null);
  const missingDays = computed(
    () => data.value?.coverage?.missing_nav_days ?? 0
  );
  /** 全周期起点标签：无论当前切到哪档都回带，让用户知道「投资以来」从哪天算 */
  const inceptionLabel = computed(() => data.value?.first_txn_date ?? null);

  function money(value?: number | null): string {
    if (value === null || value === undefined) return "—";
    return `¥${formatAmount(value)}`;
  }

  async function fetchCashFlow() {
    if (scope.ledgerId == null && scope.portfolioId == null) return;
    const params = cashFlowParams(range.value, scope);
    loadError.value = "";
    try {
      const res = await getCashFlow(params);
      data.value = res.data;
    } catch (e) {
      // 端点 400 或网络错误：如实报，不留旧图（旧图 = 假数据）
      data.value = null;
      loadError.value = errorMessageOf(e) || "资金流动数据加载失败";
      console.error("获取资金流动失败:", e);
    }
  }

  onMounted(fetchCashFlow);
  watch(() => [scope.ledgerId, scope.portfolioId, range.value], fetchCashFlow);

  return {
    range,
    data,
    loadError,
    totals,
    missingDays,
    inceptionLabel,
    money
  };
}
