/**
 * 全面盘点页（InventoryHome）数据层。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。收敛页面全部读写副作用：
 * 大类汇总 / 家庭分布 / 持仓分组 / 投资明细分页 / 按大类的资产明细（带缓存）/ 资产删除，
 * 并统一挂 `usePageRefresh` 全局刷新订阅。
 *
 * 另含 `useStrategyInsight`（#2237）：「策略洞察」区块的目标配比 / 诊断 / 行为画像读写。
 * 与上面的大盘点数据彼此独立（不共享 loading、不互相阻塞），故拆成独立 composable
 * 而非塞进 `useInventoryData` —— 否则「策略引擎接口慢」会把整个盘点页拖成加载态。
 *
 * 页面只消费本 composable 暴露的响应式状态与动作，不再直连 API。
 */

import { computed, ref, watch, type Ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteAsset,
  getAssets,
  getAssetsSummary,
  type AssetRecord
} from "@/api/assets";
import { getLedgers } from "@/api/ledger";
import { getPortfolios, type PortfolioItem } from "@/api/portfolio";
import { getPositions, updatePosition } from "@/api/positions";
import type { Position } from "@/api/types";
import {
  getAllocation,
  getEngineBehavior,
  getEngineDiagnosis,
  getEngineStrategies,
  refreshStrategyReminders,
  saveAllocation as putAllocation,
  type AllocationData,
  type AllocationTargetInput,
  type BehaviorData,
  type DiagnosisData,
  type EngineStrategyMeta
} from "@/api/strategyEngine";
import {
  getCashLikeBreakdown,
  getDistributions,
  getPositionGroups,
  type CashLikeItem,
  type DistributionsData
} from "@/api/summary";
import { usePageRefresh } from "@/composables/usePageRefresh";
import { INVESTMENT_MAJOR_KEYS } from "@/constants";
import { INVESTMENT_PAGE_SIZE } from "./constants";
import {
  buildInvestmentGroups,
  getErrorMessage,
  type AssetGroupRaw,
  type InvestmentGroup
} from "./helpers";
import {
  portfolioLabel,
  resolvePortfolioOf as resolvePortfolioAssignment
} from "./portfolioAssignModel";

/** 单次取回某大类的资产明细上限（大类下资产量级有限，一次取回避免翻页） */
const CATEGORY_ASSET_LIMIT = 500;

export function useInventoryData(activeCategory: Ref<string>) {
  /** 大类汇总金额：`{ 大类 key: 金额 }` */
  const assetsSummary = ref<Record<string, number>>({});
  /** 家庭级多维市值分布（标签栏金额口径依赖） */
  const distributions = ref<DistributionsData | null>(null);
  /** 持仓 `type` 维度分组的原始响应（投资分布卡片消费） */
  const investmentGroupsRaw = ref<AssetGroupRaw[]>([]);

  /** 投资明细分页数据（后端分页；market_value/pnl 后端暂不产出，见 Position 类型注释的已知 bug） */
  const investmentPositions = ref<Position[]>([]);
  const investmentTotal = ref(0);
  const investmentPage = ref(1);
  const investmentLoading = ref(false);

  /**
   * 组合上下文（D20 二期 UI「所属组合」列的展示与改派选项）。
   *
   * 分两块：
   * - `portfolios`：可选目标列表（浮层选项）+ id→名称映射；
   * - `ledgerPortfolioMap`：账户 → 默认组合 id。D20 的**继承路径**由服务端定义
   *   （`portfolio_service.portfolio_position_conditions`：持仓 `portfolio_id` 为 NULL 时，
   *   取其所属 `ledgers.portfolio_id`）。前端要显示「它实际归到哪个组合」必须用同一份映射，
   *   **不得另建一套推导规则**——复制第二份必然与后端漂移，而那正是这次要修的病根。
   */
  const portfolios = ref<PortfolioItem[]>([]);
  const ledgerPortfolioMap = ref<Record<number, number | null>>({});

  /**
   * 账外类现金（货基 / 逆回购）：按流水净额记账、不建持仓行，故不在持仓明细里。
   * **只用于展示，不得并入任何合计**——它的金额已经计入总资产。
   */
  const cashLikeItems = ref<CashLikeItem[]>([]);
  const cashLikeTotal = ref(0);
  const cashLikeLoading = ref(false);

  /** 当前大类的资产明细 */
  const currentAssets = ref<AssetRecord[]>([]);
  /** 按大类的资产明细缓存；资产增删改后须整体失效 */
  const assetCache = ref<Record<string, AssetRecord[]>>({});

  /** 投资分布卡片数据（仅投资理财大类有意义） */
  const investmentGroups = computed<InvestmentGroup[]>(() =>
    activeCategory.value === "investment"
      ? buildInvestmentGroups(investmentGroupsRaw.value)
      : []
  );

  /**
   * 标签栏金额（#863 口径 A 对齐）。
   *
   * 投资理财 = 持仓市值（剔除货基 / 逆回购现金等价物）+ 投资理财大类资产，
   * 直接复用后端 `get_distributions` 的 `category_distribution`「投资理财」切片（已扣现金等价物），
   * 避免标签栏比后端高一档（货基 / 逆回购应归入「流动资金」而非「投资理财」）。
   * distributions 尚未加载时回退到旧口径，保证首屏不空。
   */
  function getCategoryTotal(key: string): number {
    if (key === "investment") {
      const invEntry = distributions.value?.category_distribution?.find(
        d => d.name === "投资理财"
      );
      if (invEntry) return invEntry.value;
      return (
        (distributions.value?.positions_total_mv || 0) +
        (assetsSummary.value["investment"] || 0)
      );
    }
    return assetsSummary.value[key] || 0;
  }

  /** 投资明细：后端真实分页拉取（对齐分页信封 `{ data: Position[], total, page, per_page, message }`） */
  async function loadInvestmentPage(page: number) {
    investmentLoading.value = true;
    try {
      const res = await getPositions({ page, per_page: INVESTMENT_PAGE_SIZE });
      investmentPositions.value = res?.data ?? [];
      investmentTotal.value = res?.total ?? investmentPositions.value.length;
    } catch (e) {
      console.error("加载投资明细分页失败", e);
      investmentPositions.value = [];
    } finally {
      investmentLoading.value = false;
    }
  }

  /**
   * 拉取组合上下文（组合列表 + 账户默认组合映射）。
   *
   * 独立 try/catch 且失败时**清空而非报错**：这两个接口只服务「所属组合」列的展示与
   * 改派选项，挂了不该让整页盘点进失败态。清空后该列退化为「—」，改派浮层只剩
   * 「跟随账户」一项——看得见的降级，好过整页白屏。
   */
  async function loadPortfolioContext() {
    try {
      const [portfolioRes, ledgerRes] = await Promise.all([
        getPortfolios(),
        getLedgers()
      ]);
      portfolios.value = portfolioRes?.data ?? [];
      const map: Record<number, number | null> = {};
      for (const ledger of ledgerRes?.data ?? []) {
        map[ledger.id] = ledger.portfolio_id ?? null;
      }
      ledgerPortfolioMap.value = map;
    } catch (e) {
      console.error("加载组合上下文失败", e);
      portfolios.value = [];
      ledgerPortfolioMap.value = {};
    }
  }

  /**
   * 解析一条持仓的「所属组合」展示状态。
   *
   * 实现落在 `portfolioAssignModel.resolvePortfolioOf`（纯函数，可单测）：
   * 四态判断错一个分支，界面上都只是「换了个组合名」，看不出来，只有单测能钉住。
   * 这里只负责把响应式数据喂进去。
   */
  function resolvePortfolioOf(row: Position) {
    return resolvePortfolioAssignment(row, {
      portfolios: portfolios.value,
      ledgerPortfolioMap: ledgerPortfolioMap.value
    });
  }

  /**
   * 改派一条持仓的组合归属。
   *
   * `portfolioId = null` ⇒ 后端置 `positions.portfolio_id = NULL`，该行退回账户默认组合。
   *
   * **局部更新而不是整页 `fetchData()`**：整页重取会重拉分页数据，刚点完的那一行可能
   * 被挤出当前页——比数字短暂陈旧更让人困惑。归属列本身不参与排序，局部替换足够。
   *
   * **不主动发全局刷新事件**：改派不改变任何金额（总资产 / 市值 / 盈亏都不动），
   * 只改归属口径；组合年化属于组合详情页，进入时会重新取数，无需跨页失效。
   */
  async function reassignPosition(row: Position, portfolioId: number | null) {
    try {
      await updatePosition(row.id, { portfolio_id: portfolioId });
      const index = investmentPositions.value.findIndex(p => p.id === row.id);
      if (index >= 0) {
        investmentPositions.value[index] = {
          ...investmentPositions.value[index],
          portfolio_id: portfolioId
        };
      }
      const target =
        portfolioId == null
          ? "账户默认组合"
          : portfolioLabel(portfolios.value, portfolioId);
      ElMessage.success(`已改派到「${target}」，相关组合年化将重算`);
    } catch (e) {
      ElMessage.error(getErrorMessage(e, "改派失败"));
    }
  }

  /** 按需加载该大类的具体资产数据（命中缓存则直接复用） */
  async function loadCategoryAssets(category: string) {
    if (assetCache.value[category]) {
      currentAssets.value = assetCache.value[category];
      return;
    }
    try {
      // #1354：投资理财一次取回全部子集（investment + 5 个历史细分类），
      // 避免银行理财/信托等存量记录散落在没有入口的大类里查不到
      const major =
        category === "investment" ? INVESTMENT_MAJOR_KEYS : category;
      const res = await getAssets({
        major_category: major,
        per_page: CATEGORY_ASSET_LIMIT
      });
      const items = (res?.data ?? []) as AssetRecord[];
      assetCache.value[category] = items;
      currentAssets.value = items;
    } catch (e) {
      console.error("加载分类资产失败", e);
    }
  }

  /**
   * 拉取「类现金」明细（货基 / 逆回购的账外流水）。
   *
   * 独立 try/catch：接口挂了只让该分组不显示，不能拖垮整页盘点。
   */
  async function loadCashLike() {
    cashLikeLoading.value = true;
    try {
      const res = await getCashLikeBreakdown();
      cashLikeItems.value = res?.data?.items ?? [];
      cashLikeTotal.value = res?.data?.total_amount ?? 0;
    } catch (e) {
      console.error("加载类现金明细失败", e);
      cashLikeItems.value = [];
      cashLikeTotal.value = 0;
    } finally {
      cashLikeLoading.value = false;
    }
  }

  /**
   * 只请求基础汇总、分布与投资分组接口（不再全量拉取资产列表）。
   *
   * 资产可能刚被增删改，因此每次都先整体失效分类缓存再拉当前大类，否则列表里还留着已删记录。
   */
  async function fetchData() {
    try {
      const [summaryRes, distRes, groupsRes] = await Promise.all([
        getAssetsSummary(),
        getDistributions(),
        getPositionGroups("type")
      ]);

      // 同时兼容后端返回的【数组格式】和【旧对象格式】
      const summaryData = summaryRes?.data ?? {};
      let summaryDict: Record<string, number> = {};
      if (Array.isArray(summaryData)) {
        // 情况1：后端返回数组（[{code, value}, ...]）
        summaryData.forEach((item: { code: string; value: number }) => {
          summaryDict[item.code] = item.value;
        });
      } else {
        // 情况2：后端返回旧对象（{ cash: 0, fixed: ... }）
        summaryDict = summaryData;
      }
      assetsSummary.value = summaryDict;

      distributions.value = distRes?.data ?? null;
      investmentGroupsRaw.value = groupsRes?.data ?? [];

      // 与盘点主体并行、互不阻塞（组合上下文失败只降级「所属组合」列，不拖垮整页）
      void loadCashLike();
      void loadPortfolioContext();

      await loadInvestmentPage(investmentPage.value);

      assetCache.value = {};
      await loadCategoryAssets(activeCategory.value);
    } catch (e) {
      console.error(e);
    }
  }

  /** 删除单条资产（二次确认 → 删除 → 整页刷新） */
  async function removeAsset(row: AssetRecord) {
    try {
      await ElMessageBox.confirm(
        `确定要删除资产「${row.name}」吗？此操作不可恢复。`,
        "删除确认",
        {
          confirmButtonText: "确认删除",
          cancelButtonText: "取消",
          type: "warning"
        }
      );
      await deleteAsset(row.id);
      ElMessage.success("资产已删除");
      await fetchData();
    } catch (e) {
      if (e !== "cancel") {
        ElMessage.error(getErrorMessage(e, "删除失败"));
      }
    }
  }

  // 切换大类：拉该大类资产明细 + 投资明细分页复位到第 1 页
  watch(activeCategory, newVal => {
    loadCategoryAssets(newVal);
  });
  watch(activeCategory, () => {
    investmentPage.value = 1;
  });

  // 投资明细分页切换时重新拉取
  watch(investmentPage, page => {
    loadInvestmentPage(page);
  });

  // 账户 / 持仓数据变更后全局自动刷新
  usePageRefresh(() => {
    fetchData();
  });

  return {
    assetsSummary,
    distributions,
    investmentGroupsRaw,
    investmentGroups,
    investmentPositions,
    investmentTotal,
    investmentPage,
    investmentLoading,
    portfolios,
    resolvePortfolioOf,
    reassignPosition,
    cashLikeItems,
    cashLikeTotal,
    cashLikeLoading,
    currentAssets,
    getCategoryTotal,
    fetchData,
    removeAsset
  };
}

/**
 * 「策略洞察」区块数据层（#2237）：目标配比 + 策略引擎诊断 / 行为反推。
 *
 * 为什么独立于 `useInventoryData`：两者的数据源与失败影响面都不同——
 * 盘点数据挂了整页不可用，策略引擎挂了只该让这两张卡进失败态
 * （卡片各自 `role="alert"` + 重试，见 `WelcomeXirrTemperature` 的既有口径）。
 * 合成一个 composable 会把「引擎超时」放大成「整页空」。
 *
 * 请求失败时只置 `error` 标志、不写 0 值：0 是「真的为零」的语义，
 * 拿它当「取不到」会让人误读成「没有偏离 / 没有信号」。
 */
export function useStrategyInsight() {
  /** 目标配比（含当前占比 / 目标 / 偏离 / 越线） */
  const allocation = ref<AllocationData | null>(null);
  const allocationLoading = ref(false);
  const allocationError = ref(false);
  /** 保存中：只锁保存按钮，不遮挡列表 */
  const allocationSaving = ref(false);

  const diagnosis = ref<DiagnosisData | null>(null);
  const behavior = ref<BehaviorData | null>(null);
  /** 策略元信息：把 `strategy_code` 翻成策略名，避免直接把英文码甩给用户 */
  const strategies = ref<EngineStrategyMeta[]>([]);
  const diagnosisLoading = ref(false);
  const diagnosisError = ref(false);

  /** 「立即检查提醒」进行中 */
  const reminderRefreshing = ref(false);

  async function loadAllocation() {
    allocationLoading.value = true;
    try {
      const res = await getAllocation();
      allocation.value = res.data;
      allocationError.value = false;
    } catch (e) {
      console.error("加载目标配比失败", e);
      allocationError.value = true;
    } finally {
      allocationLoading.value = false;
    }
  }

  async function loadDiagnosis() {
    diagnosisLoading.value = true;
    try {
      const [strategyRes, diagnosisRes, behaviorRes] = await Promise.all([
        getEngineStrategies(),
        getEngineDiagnosis(),
        getEngineBehavior()
      ]);
      strategies.value = strategyRes.data ?? [];
      diagnosis.value = diagnosisRes.data ?? null;
      behavior.value = behaviorRes.data ?? null;
      diagnosisError.value = false;
    } catch (e) {
      console.error("加载策略诊断失败", e);
      diagnosisError.value = true;
    } finally {
      diagnosisLoading.value = false;
    }
  }

  /** 两张卡并行加载；任一失败只影响自己那张卡 */
  async function loadStrategyInsight() {
    await Promise.all([loadAllocation(), loadDiagnosis()]);
  }

  /**
   * 保存目标配比（整体覆盖语义）。
   *
   * 刻意**不 catch**：失败提示由 http 拦截器统一给出，这里吞掉反而会让人以为保存成功。
   * `finally` 只负责解锁按钮。
   */
  async function saveTargets(items: AllocationTargetInput[]) {
    allocationSaving.value = true;
    try {
      const res = await putAllocation(items);
      allocation.value = res.data;
      ElMessage.success(
        `已保存 ${res.data.saved_count ?? items.length} 条目标配比`
      );
    } finally {
      allocationSaving.value = false;
    }
  }

  /**
   * 立即检查提醒：跑一次偏离扫描并写站内通知。
   * 同样不 catch —— 失败提示交给拦截器。
   */
  async function refreshReminders() {
    reminderRefreshing.value = true;
    try {
      const res = await refreshStrategyReminders();
      const created = res.data?.created ?? 0;
      if (created > 0) {
        ElMessage.success(`新增 ${created} 条提醒，可在右上角铃铛查看`);
      } else {
        ElMessage.info("当前没有越线的配比");
      }
    } finally {
      reminderRefreshing.value = false;
    }
  }

  // 持仓 / 账户变更后（导入、记账等）目标配比与诊断都要跟着变
  usePageRefresh(() => {
    void loadStrategyInsight();
  });

  return {
    allocation,
    allocationLoading,
    allocationError,
    allocationSaving,
    diagnosis,
    behavior,
    strategies,
    diagnosisLoading,
    diagnosisError,
    reminderRefreshing,
    loadStrategyInsight,
    loadAllocation,
    loadDiagnosis,
    saveTargets,
    refreshReminders
  };
}
