/**
 * 账户详情页「持仓所属组合」域（D20 二期 UI；#2922 从 `useLedgerDetail` 下沉）。
 *
 * ## 边界
 *
 * 本域只回答一个问题：**这条持仓归哪个组合**——读取（`resolveHoldingPortfolio`）、
 * 改派（`reassignPosition`）、候选项与上下文就绪位（`loadPortfolioContext`）。
 * 解析规则本身不在这里写：显式指派压过账户继承是**服务端口径**
 * （`portfolio_service.portfolio_position_conditions`），前端唯一投影是
 * `views/asset/inventory/portfolioAssignModel` 的纯函数，此处只喂参数。
 *
 * ## 为什么不进 store
 *
 * 全是单页派生：组合列表为「本页那条持仓的改派浮层」而拉，账户默认组合来自本页
 * 路由上的那个账户。跨页共享为零，进 store 只会留下一份路由切换后仍然陈旧的
 * 组合列表（#2922 判据：只有跨页共享的状态才值得进 store）。
 */
import { computed, ref } from "vue";
import type { ComputedRef, Ref } from "vue";
import { ElMessage } from "element-plus";
import type { LedgerItem } from "@/api/ledger";
import { getPortfolios, type PortfolioItem } from "@/api/portfolio";
import { updatePosition } from "@/api/positions";
import type { LedgerHoldingRow } from "@/composables/useLedgerDetail";
import {
  portfolioLabel,
  resolvePortfolioOf,
  type PortfolioAssignment,
  type PortfolioLookup
} from "@/views/asset/inventory/portfolioAssignModel";

export interface LedgerPositionPortfolioApi {
  portfolioList: Ref<PortfolioItem[]>;
  loadPortfolioContext: () => Promise<void>;
  /** 编辑账户弹窗自行拉到的组合列表（含失败重试成功）也走这里，放行本页解析 */
  adoptPortfolioList: (list: PortfolioItem[]) => void;
  /** 账本列表到位（继承态要判「本账户默认组合」，缺它只能显示「—」） */
  markLedgersLoaded: () => void;
  resolveHoldingPortfolio: (row: LedgerHoldingRow) => PortfolioAssignment;
  reassignPosition: (
    row: LedgerHoldingRow,
    portfolioId: number | null
  ) => Promise<void>;
}

export function useLedgerPositionPortfolio(options: {
  ledgerIdNum: ComputedRef<number | undefined>;
  accountInfo: ComputedRef<LedgerItem | null>;
  holdingsList: Ref<LedgerHoldingRow[]>;
}): LedgerPositionPortfolioApi {
  const { ledgerIdNum, accountInfo, holdingsList } = options;

  const portfolioList = ref<PortfolioItem[]>([]);

  /**
   * 「所属组合」列的上下文就绪位。
   *
   * 继承态（「随账户」）要成立，光有组合列表不够——还得知道**本账户的默认组合**
   * （来自 `ledgers → accountInfo`）。两路数据任一未到时若按「查不到 ⇒ 没设默认组合」
   * 直接判成 `none`，界面就会把「不知道」显示成「未归属」：用户看到自己的持仓
   * 忽然不属于任何组合，只会以为数据丢了。
   *
   * 故未就绪时一律走 `unknown`（显示「—」），宁可少说，不可错说。
   */
  const portfoliosLoaded = ref(false);
  const ledgersLoaded = ref(false);

  /** 组合上下文是否可用于解析归属（两个来源都到齐，见 portfoliosLoaded 注释） */
  const portfolioContextReady = computed(
    () => portfoliosLoaded.value && ledgersLoaded.value
  );

  /** 供纯函数解析用的查询表：本页只有一个账户，故映射里只有一条 */
  const portfolioLookup = computed<PortfolioLookup>(() => ({
    portfolios: portfolioList.value,
    ledgerPortfolioMap:
      ledgerIdNum.value != null
        ? { [ledgerIdNum.value]: accountInfo.value?.portfolio_id ?? null }
        : {}
  }));

  /**
   * 解析单条持仓的归属状态。
   *
   * 规则本身**不在这里写**：显式指派压过账户继承是服务端口径
   * （`portfolio_service.portfolio_position_conditions`），抄第二份必然漂移，
   * 故直接调盘点页那份纯函数。本函数只补两件本页特有的事：
   * 1. 未就绪 → `unknown`（不猜）；
   * 2. 补 `ledger_id`——账户持仓接口的行里**没有**该字段（items 是后端手工拼的
   *    字典），而整页只有一个账户，用路由上的 id 补上比让后端多发一个冗余字段更省。
   */
  function resolveHoldingPortfolio(row: LedgerHoldingRow): PortfolioAssignment {
    if (!portfolioContextReady.value) {
      return { mode: "unknown", labelText: null };
    }
    return resolvePortfolioOf(
      { ...row, ledger_id: ledgerIdNum.value ?? null },
      portfolioLookup.value
    );
  }

  /**
   * 改派持仓所属组合。
   *
   * ⚠️ 必须走 `PATCH /api/positions/<id>/`，**不是**账户下的嵌套持仓 PATCH
   * （`/api/ledgers/<lid>/positions/<pid>/`）。后者是「五笔钱」白名单，只接受
   * allocation / current_price / notes，`portfolio_id` 会被静默丢弃——请求返回 200、
   * 界面却纹丝不动，是最难排查的一类「失败」。`api/ledger.ts` 里该函数的注释
   * 也明确写着「迁移持仓归属请改调 PATCH /api/positions/<id>/」。
   *
   * 成功后**局部替换该行**而不整页重取：改派不动任何金额，重取只会让表格闪一下，
   * 还会把刚改的那行挤出当前页（后端按市值降序分页）。
   */
  async function reassignPosition(
    row: LedgerHoldingRow,
    portfolioId: number | null
  ): Promise<void> {
    try {
      await updatePosition(row.id, { portfolio_id: portfolioId });
    } catch (e) {
      const err = e as {
        message?: string;
        response?: { data?: { message?: string; description?: string } };
      };
      ElMessage.error(
        err?.response?.data?.message ||
          err?.response?.data?.description ||
          err?.message ||
          "改派组合失败"
      );
      return;
    }
    const index = holdingsList.value.findIndex(item => item.id === row.id);
    if (index >= 0) {
      holdingsList.value[index] = {
        ...holdingsList.value[index],
        portfolio_id: portfolioId
      };
    }
    const target =
      portfolioId === null
        ? "账户默认组合"
        : portfolioLabel(portfolioList.value, portfolioId);
    ElMessage.success(`已改派到「${target}」，相关组合年化将重算`);
  }

  /**
   * 拉取组合列表（改派浮层的候选项）。
   *
   * 首屏就拉：此前只在「编辑账户」弹窗里才拉（下拉需要），于是打开页面时组合列
   * 无从解析。失败不抛——组合列降级为「—」，持仓表其余列照常可用。
   */
  async function loadPortfolioContext() {
    try {
      const res = await getPortfolios();
      adoptPortfolioList((res as { data?: PortfolioItem[] })?.data ?? []);
    } catch (e) {
      console.error("组合列表加载失败，「所属组合」列暂显示为「—」", e);
    }
  }

  /** 组合列表到位即放行解析（首屏那次与编辑弹窗的重试都经此处） */
  function adoptPortfolioList(list: PortfolioItem[]) {
    portfolioList.value = list;
    portfoliosLoaded.value = true;
  }

  function markLedgersLoaded() {
    ledgersLoaded.value = true;
  }

  return {
    portfolioList,
    loadPortfolioContext,
    adoptPortfolioList,
    markLedgersLoaded,
    resolveHoldingPortfolio,
    reassignPosition
  };
}
