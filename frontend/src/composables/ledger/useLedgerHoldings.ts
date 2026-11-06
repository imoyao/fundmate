/**
 * 账户详情页「持仓域」：持仓列表的分页 / 搜索 / 取数（#2948，D89）。
 *
 * ## 只切「状态与请求」，不切「编排」
 *
 * 父文件 `onMounted` 里是这样（顺序是实测踩出来的，注释也写在原处）：
 *
 * ```ts
 * await Promise.all([loadSummary(), loadHoldings(), loadPortfolioContext()]);
 * if (summaryData?.ledger_type === "fund") await loadMoneyFundIncome();
 * ```
 *
 * 货基收益**必须**在 summary 之后——它依赖 summary 判定账户类型。这是**时序**，
 * 不是**状态**：把编排一起搬进来，三条约束就会被藏进子域，日后改一处要跨文件推理。
 * 故边界定为：子域只保证「给什么 page 就按什么 page 取数」，**何时取**仍归父文件。
 *
 * ## 为什么不进 store
 *
 * 与 `useLedgerOverview` 同理：单页派生，一次路由进出即弃，跨页共享为零。搬进 store
 * 只会让「页面卸载后还留着一份陈旧持仓列表」成为可能——那是把大文件换个位置。
 */
import { ref } from "vue";
import type { ComputedRef, Ref } from "vue";
import { ElMessage } from "element-plus";
import { getLedgerPositions } from "@/api/ledger";
import type { LedgerHoldingRow } from "./types";

export interface LedgerHoldingsApi {
  /** 当前页（**请求前**即更新，供分页器立即回显目标页，见 `loadHoldings` 注释） */
  holdingsPage: Ref<number>;
  holdingsPageSize: number;
  holdingsList: Ref<LedgerHoldingRow[]>;
  holdingsTotal: Ref<number>;
  /** 名称/代码搜索（#982）：后端 LIKE 过滤，防抖后由父文件重置回第一页 */
  holdingsSearch: Ref<string>;
  loadHoldings: (page?: number) => Promise<void>;
}

/**
 * @param ledgerId 路由参数里的账户 id（原样字符串，伪账户是 `unclassified`）
 */
export function useLedgerHoldings(
  ledgerId: ComputedRef<string>
): LedgerHoldingsApi {
  const holdingsPage = ref(1);
  const holdingsPageSize = 20;
  const holdingsList = ref<LedgerHoldingRow[]>([]);
  const holdingsTotal = ref(0);
  // 名称/代码搜索（#982）：后端 LIKE 过滤，防抖后重置回第一页
  const holdingsSearch = ref("");

  /**
   * 取持仓。默认第一页（首屏 / 全局刷新 / 迁移后刷新 / Tab 切回都走默认值）。
   *
   * ⚠️ 两处行为是**既有契约**，搬过来时逐字保留，别「顺手修」：
   *
   * 1. `holdingsPage.value = page` 在**请求之前**赋值。分页器据此立即回显用户点的页；
   *    若等响应回来再改，慢网下会出现「点了第 3 页、页码跳回第 1 页再跳回第 3 页」。
   *    请求失败时页码也**不回滚**——列表仍是上一页数据，页码停在目标页，属已知取舍。
   * 2. 失败只提示、**不清空列表**。清空会让一次网络抖动变成「持仓全没了」，比留住
   *    上一页陈旧数据糟得多。
   */
  async function loadHoldings(page = 1) {
    holdingsPage.value = page;
    try {
      const res = await getLedgerPositions(Number(ledgerId.value), {
        page,
        per_page: holdingsPageSize,
        search: holdingsSearch.value.trim() || undefined
      });
      const result = (
        res as { data?: { items?: LedgerHoldingRow[]; total?: number } }
      )?.data;
      // 契约缺失一律按空处理（同 AGENTS.md「缺失一律 null」那条）：后端字段缺失时
      // 不能让 ref 变成 undefined——模板里的 `holdingsTotal > 0` 会静默恒假。
      holdingsList.value = result?.items ?? [];
      holdingsTotal.value = result?.total ?? 0;
    } catch {
      ElMessage.error("持仓加载失败");
    }
  }

  return {
    holdingsPage,
    holdingsPageSize,
    holdingsList,
    holdingsTotal,
    holdingsSearch,
    loadHoldings
  };
}
