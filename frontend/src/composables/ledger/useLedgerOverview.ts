/**
 * 账户详情页「概览域」：概览数据、货基收益、资产构成（#2922，从 `useLedgerDetail` 下沉）。
 *
 * ## 为什么这一块单独成域
 *
 * 它只依赖一个**只读输入**（路由上的账户 id），产出的全是**本页内的派生视图**，
 * 与持仓列表、交易流水、弹窗开关没有交集。原先挤在 845 行的 `useLedgerDetail` 里，
 * 与「账户信息 / 列表加载 / 归档 / 删除 / 迁移」混排，改任一处都得先读完整个文件
 * 确认影响面。
 *
 * ## 刻意不进 store
 *
 * 这些数据是**单页派生**（一次路由进出即弃），跨页共享为零。搬进 store 只会
 * 让「页面卸载后还留着一份陈旧概览」成为可能——那是把大文件搬个位置，不是
 * 状态归属变清楚（#2922 卡面的判据）。
 */
import { computed, ref } from "vue";
import type { ComputedRef, Ref } from "vue";
import { ElMessage } from "element-plus";
import { getLedgerSummary } from "@/api/ledger";
import {
  getMoneyFundIncome,
  type MoneyFundIncomeData
} from "@/api/performance";
import type { TodayPnlData } from "@/api/summary";
import { useTodayPnlGroups } from "@/composables/useTodayPnlGroups";
import type { LedgerSummaryData } from "./types";

export interface LedgerOverviewApi {
  summaryData: Ref<LedgerSummaryData | null>;
  moneyFundData: Ref<MoneyFundIncomeData | null>;
  /** 账户级当日估值（`today-pnl?ledger_id=...`）；与货基收益是两套口径，不相加 */
  todayPnlData: Ref<TodayPnlData | null>;
  isCompositionLedger: ComputedRef<boolean>;
  compositionData: ComputedRef<{ name: string; value: number }[]>;
  compositionColorMap: Record<string, string>;
  loadSummary: () => Promise<void>;
  loadMoneyFundIncome: () => Promise<void>;
}

/**
 * @param ledgerId 路由参数里的账户 id（原样字符串，取数前自行转数字）
 */
export function useLedgerOverview(
  ledgerId: ComputedRef<string>
): LedgerOverviewApi {
  const summaryData = ref<LedgerSummaryData | null>(null);

  // 货币基金收益（仅基金账户拉取）
  const moneyFundData = ref<MoneyFundIncomeData | null>(null);

  // D92 账户级当日估值：维度默认 class，作用域由路由 id 决定。
  // 用 getter 传参，切账户时底座会自动重取，不会残留上一个账户的数。
  // 与 `moneyFundData`（货基净值收益）并列展示，二者口径不同、禁止相加。
  const { data: todayPnlData } = useTodayPnlGroups(() => ({
    ledger_id: Number(ledgerId.value)
  }));

  // 是否展示资产构成（仅股票 / 基金 / 信用账户有投资资产与现金类资产之分）
  const isCompositionLedger = computed(() =>
    ["stock", "fund", "e_account"].includes(
      summaryData.value?.ledger_type ?? ""
    )
  );

  // 环形图数据：投资资产 vs 现金类资产。
  //
  // ⚠️ 两片必须是**持仓市值的一个划分**（合计 = 左侧「总资产」），否则占比会算出
  // 负数或超过 100%：账外类现金（孤儿货基流水净额 / 账户现金）不在持仓市值内，
  // 若拿它当「现金类资产」片，投资片 = 总市值 - 类现金 就会变负
  // （真机：账户 id=12 曾显示「投资资产 -63.2% / 现金类资产 163.2%」）。
  // 故现金片固定取 `cash_like_in_positions_amount`（持仓内类现金）。
  const compositionData = computed(() => [
    { name: "投资资产", value: summaryData.value?.investment_amount ?? 0 },
    {
      name: "现金类资产",
      value: summaryData.value?.cash_like_in_positions_amount ?? 0
    }
  ]);

  // 环形图配色：走 design.md 图表语义变量（禁止硬编码 hex），对齐家庭资产看板饼图取色（chart-01 起）
  const compositionColorMap = {
    投资资产: "--chart-01",
    现金类资产: "--chart-06"
  };

  async function loadSummary() {
    try {
      const res = await getLedgerSummary(Number(ledgerId.value));
      summaryData.value = (res as { data?: LedgerSummaryData })?.data ?? {};
    } catch {
      ElMessage.error("概览加载失败");
    }
  }

  async function loadMoneyFundIncome() {
    moneyFundData.value = null;
    try {
      const res = await getMoneyFundIncome({
        scope: "ledger",
        ledger_id: Number(ledgerId.value)
      });
      moneyFundData.value = res.data;
    } catch (e) {
      // 禁止静默吞错：失败保留占位 "--"，仅记日志不打断页面
      console.error("货基收益加载失败", e);
    }
  }

  return {
    summaryData,
    moneyFundData,
    todayPnlData,
    isCompositionLedger,
    compositionData,
    compositionColorMap,
    loadSummary,
    loadMoneyFundIncome
  };
}
