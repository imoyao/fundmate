import { asErrorEnvelope, errorMessageOf } from "@/utils/errorMessage";
import {
  ref,
  computed,
  reactive,
  onMounted,
  shallowRef,
  type Ref,
  type ComputedRef
} from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  getLedgers,
  deleteLedgerPosition,
  archiveLedger,
  unarchiveLedger,
  getSalesInstitutions,
  type LedgerItem,
  type SalesInstitution
} from "@/api/ledger";
import { getPortfolios, type PortfolioItem } from "@/api/portfolio";
import type { PortfolioAssignment } from "@/views/asset/inventory/portfolioAssignModel";
import type { MoneyFundIncomeData } from "@/api/performance";
import type { TodayPnlData } from "@/api/summary";
import { getLedgerTypeLabel } from "@/constants";
import { usePageRefresh } from "@/composables/usePageRefresh";
import { useLedgerOverview } from "@/composables/ledger/useLedgerOverview";
import { useLedgerHoldings } from "@/composables/ledger/useLedgerHoldings";
import { useLedgerPositionPortfolio } from "@/composables/ledger/useLedgerPositionPortfolio";

import type { LedgerHoldingRow, LedgerSummaryData } from "./ledger/types";

/**
 * 三个行 / 概览类型已迁到 `./ledger/types`（#2931，D87）：`ledger/` 两个子域与视图组件
 * 直接引用该文件，不再反向依赖本 composable。此处 re-export 只为保持对外 import 路径不变。
 */
export type {
  CashLikeBreakdownRow,
  LedgerHoldingRow,
  LedgerSummaryData
} from "./ledger/types";

/** 子组件命令式打开入口的结构类型（避免 composable 反向依赖视图组件） */
interface MigrateDialogInstance {
  openMigrateDialog: (row: LedgerHoldingRow) => void;
}
interface MigrationPanelInstance {
  openBatchMigrateDialog: () => void;
}

/**
 * 交易 composable 反向绑定所需的最小接口（避免 useLedgerDetail 反向 import useLedgerTransactions，
 * 从而打破循环类型依赖）。useLedgerTransactions 传入的是完整 LedgerTransactionsApi，可赋值至此。
 */
interface LedgerTransactionsBinding {
  transactionsSearch: Ref<string>;
  transactionsList: Ref<unknown[]>;
  loadTransactions: (page?: number) => Promise<void>;
  resetCache: () => void;
}

export interface LedgerDetailApi {
  ledgerId: ComputedRef<string>;
  ledgerIdNum: ComputedRef<number | undefined>;
  loading: Ref<boolean>;
  showSkeleton: Ref<boolean>;
  ledgers: Ref<LedgerItem[]>;
  portfolioList: Ref<PortfolioItem[]>;
  salesInstitutions: Ref<SalesInstitution[]>;
  deleteDialogVisible: Ref<boolean>;
  deletingAccount: Ref<LedgerItem | null>;
  showEditDialog: Ref<boolean>;
  drawerVisible: Ref<boolean>;
  selectedPosition: Ref<LedgerHoldingRow | null>;
  summaryData: Ref<LedgerSummaryData | null>;
  moneyFundData: Ref<MoneyFundIncomeData | null>;
  /** 账户级当日估值（D92，由 useLedgerOverview 透传） */
  todayPnlData: Ref<TodayPnlData | null>;
  isCompositionLedger: ComputedRef<boolean>;
  compositionData: ComputedRef<{ name: string; value: number }[]>;
  compositionColorMap: Record<string, string>;
  accountInfo: ComputedRef<LedgerItem | null>;
  accountName: ComputedRef<string>;
  subTitle: ComputedRef<string>;
  getAllocColor: (alloc: string | null) => string;
  cashLedgers: ComputedRef<LedgerItem[]>;
  sameTypeLedgers: ComputedRef<LedgerItem[]>;
  activeTab: Ref<string>;
  activeSearch: ComputedRef<string>;
  onSearchInput: () => void;
  holdingsPage: Ref<number>;
  holdingsPageSize: number;
  holdingsList: Ref<LedgerHoldingRow[]>;
  holdingsTotal: Ref<number>;
  loadHoldings: (page?: number) => Promise<void>;
  /**
   * 解析一条持仓的「所属组合」归属（显式指派 / 随账户继承 / 未归属 / 未知）。
   * 账户详情页表格的「所属组合」列据此渲染，解析规则本身在
   * `views/asset/inventory/portfolioAssignModel`（服务端口径的前端唯一投影）。
   */
  resolveHoldingPortfolio: (row: LedgerHoldingRow) => PortfolioAssignment;
  /** 改派持仓所属组合；`null` = 退回账户默认组合继承 */
  reassignPosition: (
    row: LedgerHoldingRow,
    portfolioId: number | null
  ) => Promise<void>;
  openPositionDrawer: (row: LedgerHoldingRow) => void;
  /**
   * 只重取账户概览（不含持仓 / 流水）。
   *
   * 供「账户概览以外的轻量写入」定点刷新用：账户现金（G5）写入后只有
   * `account_cash_amount` / `cash_like_amount` 变了，重取整页数据属浪费。
   */
  loadSummary: () => Promise<void>;
  /** 持仓抽屉内改/删交易后：概览 + 持仓行 + 交易记录 Tab 全部重取（后端已重算份额成本） */
  refreshAfterPositionTxnChange: () => Promise<void>;
  openEditDialog: () => Promise<void>;
  toggleArchiveDetail: (ledger: LedgerItem) => Promise<void>;
  /** 打开删除持仓确认对话框（#1830：删除分支收进对话框，取消位归位） */
  openDeletePositionDialog: (row: LedgerHoldingRow) => void;
  closeDeletePositionDialog: () => void;
  handleDeletePosition: (payload: {
    keepTransactions: boolean;
  }) => Promise<void>;
  /** 删除持仓对话框状态（visible / loading / 目标持仓） */
  deletePositionDialog: {
    visible: boolean;
    loading: boolean;
    positionId: number | null;
    positionName: string;
  };
  openDeleteDialog: (account: LedgerItem) => void;
  onAccountUpdated: () => Promise<void>;
  onMigrationCommitted: () => void;
  onTabChange: (tabName: string) => void;
  migrateDialogRef: Ref<MigrateDialogInstance | null>;
  migrationPanelRef: Ref<MigrationPanelInstance | null>;
  bindTransactions: (api: LedgerTransactionsBinding) => void;
}

/**
 * 账本详情页「详情与账户信息」相关状态与函数：详情加载、账户信息、销售机构候选、
 * 概览/货基/持仓 Tab 数据、搜索联动、归档/编辑/删除、全局刷新与首屏加载。
 * 交易流水 Tab 的状态与函数见 useLedgerTransactions。
 * 共享状态（ledgers / accountInfo / salesInstitutions / ledgerId / accountName 等）统一在此持有，
 * 其余 composable 通过参数复用同一实例，避免重复声明导致状态分裂。
 */
export function useLedgerDetail(): LedgerDetailApi {
  const route = useRoute();

  const ledgerId = computed(() => route.params.id as string);
  /**
   * 账户 id（数字口径）。
   *
   * ⚠️ 不要用 `Number(ledgerId.value)` 顶替：路由参数是**字符串**，非数字取值
   * （历史遗留的 `/asset/ledgers/<非数字>` 深链、空值）经 Number 之后是 **NaN**；
   * NaN 会被 axios 序列化成 `ledger_id=NaN`，后端
   * `request.args.get('ledger_id', type=int)` 解析失败一律回 None
   * （＝「不传」＝家庭级）——于是页面拿**全家庭**的数据当本页展示，而面板的
   * 口径标签还写着「账户」。数据与标签同时错，比单错更坏。
   *
   * 故只认**有限数字**：非数字 / 空值一律 undefined，即「显式不传」，
   * 由各消费方自己落到家庭级或整块不展示。
   */
  const ledgerIdNum = computed<number | undefined>(() => {
    const raw = ledgerId.value;
    if (!raw) return undefined;
    const n = Number(raw);
    return Number.isFinite(n) ? n : undefined;
  });

  const loading = ref(true);
  // 骨架屏阈值控制：请求 ≤200ms 返回时直接渲染内容、跳过骨架屏，避免"闪屏"（骨架刚出现就消失）
  const showSkeleton = ref(false);
  let skeletonTimer: ReturnType<typeof setTimeout> | null = null;
  const ledgers = ref<LedgerItem[]>([]);
  /** 基金销售机构候选（AMAC 名录，编辑账户可选关联） */
  const salesInstitutions = ref<SalesInstitution[]>([]);
  const deleteDialogVisible = ref(false);
  const deletingAccount = ref<LedgerItem | null>(null);

  const showEditDialog = ref(false);

  const drawerVisible = ref(false);
  const selectedPosition = ref<LedgerHoldingRow | null>(null);

  // 概览 / 货基收益 / 资产构成（#2922 下沉到 useLedgerOverview：只依赖账户 id
  // 一个只读输入，产出全是本页派生视图，不进 store）
  const {
    summaryData,
    moneyFundData,
    todayPnlData,
    isCompositionLedger,
    compositionData,
    compositionColorMap,
    loadSummary,
    loadMoneyFundIncome
  } = useLedgerOverview(ledgerId);

  // 持仓 Tab 数据（#2948，D89 下沉到 useLedgerHoldings：分页状态与取数属该域；
  // 「何时取」（首屏 Promise.all 顺序 / 搜索防抖 / 刷新时机）仍留本文件，见 onMounted）
  const {
    holdingsPage,
    holdingsPageSize,
    holdingsList,
    holdingsTotal,
    holdingsSearch,
    loadHoldings
  } = useLedgerHoldings(ledgerId);

  const activeTab = ref("holdings");

  // 交易 composable 反向绑定入口：搜索 / 全局刷新 / 删除持仓时联动交易列表
  // 用 shallowRef 避免 ref 的 UnwrapRef 把绑定对象内的 Ref<string> 等字段递归解包
  const transactionsApi = shallowRef<LedgerTransactionsBinding | null>(null);
  function bindTransactions(api: LedgerTransactionsBinding) {
    transactionsApi.value = api;
  }

  /** 当前激活 Tab 的搜索词代理：一个输入框服务两个列表 */
  const activeSearch = computed({
    get: () =>
      activeTab.value === "holdings"
        ? holdingsSearch.value
        : (transactionsApi.value?.transactionsSearch.value ?? ""),
    set: (v: string) => {
      if (activeTab.value === "holdings") holdingsSearch.value = v;
      else if (transactionsApi.value)
        transactionsApi.value.transactionsSearch.value = v;
    }
  });

  /** 搜索防抖（300ms）：变更即重置回第一页；输入框按当前 Tab 经 activeSearch 绑定 */
  const searchTimers: Record<"holdings" | "transactions", number | undefined> =
    {
      holdings: undefined,
      transactions: undefined
    };

  function onSearchInput() {
    const tab = activeTab.value === "holdings" ? "holdings" : "transactions";
    if (searchTimers[tab]) window.clearTimeout(searchTimers[tab]);
    searchTimers[tab] = window.setTimeout(() => {
      if (tab === "holdings") void loadHoldings(1);
      else void transactionsApi.value?.loadTransactions(1);
    }, 300);
  }

  // 账户信息
  const accountInfo = computed(
    () => ledgers.value.find(l => String(l.id) === ledgerId.value) || null
  );
  const accountName = computed(
    () =>
      accountInfo.value?.name || summaryData.value?.ledger_name || "账户详情"
  );

  const subTitle = computed(() => {
    const type =
      summaryData.value?.ledger_type || accountInfo.value?.ledger_type;
    return getLedgerTypeLabel(type) || "其他";
  });

  // 五笔钱颜色映射
  function getAllocColor(alloc: string | null): string {
    const colorMap: Record<string, string> = {
      liquid: "var(--sankey-liquid)",
      stable: "var(--sankey-stable)",
      longterm: "var(--sankey-longterm)",
      speculative: "var(--sankey-speculative)",
      security: "var(--sankey-security)"
    };
    return colorMap[alloc || ""] || "var(--text-tertiary)";
  }

  // 关联现金账户列表
  const cashLedgers = computed(() =>
    ledgers.value.filter(l => l.ledger_type === "bank")
  );
  const sameTypeLedgers = computed(() =>
    accountInfo.value
      ? ledgers.value.filter(
          l =>
            l.ledger_type === accountInfo.value!.ledger_type &&
            l.id !== Number(ledgerId.value)
        )
      : []
  );

  function openPositionDrawer(row: LedgerHoldingRow) {
    selectedPosition.value = row; // 把当前点击的持仓数据传进去
    drawerVisible.value = true; // 打开抽屉
  }

  async function handleGlobalRefresh() {
    console.log("收到全局记账完成信号，刷新当前页面数据...");
    await loadSummary();
    await loadHoldings();
    // 如果当前用户正在看的是交易记录 Tab，顺便刷新交易记录
    if (activeTab.value === "transactions") {
      await transactionsApi.value?.loadTransactions();
    }
  }

  /**
   * 持仓抽屉里改/删交易后的定点刷新。
   *
   * 后端（`transactions.delete`）删完会按剩余流水回滚份额与成本，编辑同理，因此过期的
   * 有三处：页头概览（市值/成本）、持仓 Tab 的该行份额、交易记录 Tab（同一批流水）。
   * 抽屉头部绑的是 `holdingsList` 里的对象，而 `loadHoldings()` 会整表替换成新对象，
   * 旧引用会停在旧份额上——必须按 id 重新绑定，否则抽屉里的份额与外面永远对不上。
   * 持仓若被删除（只剩锚点/无流水），顺手关掉抽屉，避免停在一条不存在的持仓上。
   */
  async function refreshAfterPositionTxnChange() {
    await Promise.all([loadSummary(), loadHoldings(holdingsPage.value)]);
    const current = selectedPosition.value;
    if (current) {
      const fresh = holdingsList.value.find(
        h => String(h.id) === String(current.id)
      );
      if (fresh) {
        selectedPosition.value = fresh;
      } else {
        selectedPosition.value = null;
        drawerVisible.value = false;
      }
    }
    await transactionsApi.value?.loadTransactions(1);
  }

  /** 销售机构候选加载：失败仅记日志，编辑弹窗下拉留空（可选字段不阻塞页面） */
  async function loadSalesInstitutions() {
    try {
      const res = await getSalesInstitutions();
      salesInstitutions.value = res?.data ?? [];
    } catch (e) {
      console.error("销售机构名录加载失败", e);
    }
  }

  // 持仓加载已下沉到 useLedgerHoldings（#2948，D89），本文件只保留「何时调它」的编排

  // ── 所属组合（D20 二期 UI，2026-11-05）──────────────────────────────
  //
  // 账户详情页此前只能改「配置目标」（五笔钱），组合归属得跑去「全面盘点」页改。
  // 而用户看账户时最想问的正是「这个账户里哪些持仓被我拆到了别的组合」——
  // 数据就在眼前，入口却在另一页。这一组把它补上。
  //
  // #2922 起整块下沉到 useLedgerPositionPortfolio（读归属 / 改派 / 候选项与就绪位）；
  // 同属单页派生，不进 store。
  const {
    portfolioList,
    loadPortfolioContext,
    adoptPortfolioList,
    markLedgersLoaded,
    resolveHoldingPortfolio,
    reassignPosition
  } = useLedgerPositionPortfolio({
    ledgerIdNum,
    accountInfo,
    holdingsList
  });

  function onTabChange(tabName: string) {
    if (tabName === "holdings" && holdingsList.value.length === 0) {
      loadHoldings();
    } else if (
      tabName === "transactions" &&
      (transactionsApi.value?.transactionsList.value.length ?? 0) === 0
    ) {
      transactionsApi.value?.loadTransactions();
    }
  }

  // 原有的 openEditDialog
  async function openEditDialog() {
    if (!accountInfo.value) return;

    // 🔥 新增：点开编辑弹窗时，才去拉取关联的下拉列表数据
    try {
      // 为了不阻塞用户体验，可以加个 loading
      const [ledgerRes, portfolioRes] = await Promise.all([
        getLedgers(),
        getPortfolios()
      ]);
      ledgers.value = ledgerRes.data ?? [];
      // 首屏那一次若失败，这里重试成功后同样要放行「所属组合」列的解析
      adoptPortfolioList(
        (portfolioRes as { data?: PortfolioItem[] })?.data ?? []
      );
    } catch {
      ElMessage.error("加载关联账户或组合列表失败");
      return; // 加载失败不打开弹窗
    }

    // 表单回填与快照由 EditAccountDialog 在 visible 变为 true 时自行处理
    showEditDialog.value = true;
  }

  /** 详情页归档/激活：归档给一次确认（保留全部数据、仅隐藏） */
  async function toggleArchiveDetail(ledger: LedgerItem) {
    const archiving = ledger.is_active !== false;
    try {
      if (archiving) {
        await ElMessageBox.confirm(
          `归档后「${ledger.name}」将从日常列表隐藏，但全部交易/持仓数据仍保留并计入收益。确定归档？`,
          "归档账户",
          {
            confirmButtonText: "归档",
            cancelButtonText: "取消",
            type: "warning"
          }
        );
      }
      if (archiving) {
        await archiveLedger(ledger.id);
        ElMessage.success(`已归档「${ledger.name}」`);
      } else {
        await unarchiveLedger(ledger.id);
        ElMessage.success(`已激活「${ledger.name}」`);
      }
      // 刷新账户信息（accountInfo 由 ledgers 派生）+ 顶部统计
      const res = await getLedgers(true);
      ledgers.value = res.data ?? [];
      await loadSummary();
      await loadHoldings();
    } catch (e) {
      if (e !== "cancel" && asErrorEnvelope(e).action !== "cancel") {
        ElMessage.error(errorMessageOf(e) || "操作失败");
      }
    }
  }

  /**
   * 删除持仓确认（#1830）。
   *
   * 旧实现用 `ElMessageBox.confirm` 并把 `cancelButtonText` 写成「仅删除持仓」——
   * 「取消」这个中止位被劫持成一次真实删除，想反悔的用户点下去持仓真被删。
   * 现在改为对话框（`DeletePositionDialog`），三个动作各自自解释：
   * 取消 / 仅删除持仓（保留交易）/ 删除持仓及交易（danger）。
   */
  const deletePositionDialog = reactive({
    visible: false,
    loading: false,
    positionId: null as number | null,
    positionName: ""
  });

  function openDeletePositionDialog(row: LedgerHoldingRow) {
    deletePositionDialog.positionId = row.id;
    deletePositionDialog.positionName = row.name || row.symbol || "";
    deletePositionDialog.visible = true;
  }

  function closeDeletePositionDialog() {
    if (deletePositionDialog.loading) return;
    deletePositionDialog.visible = false;
  }

  async function handleDeletePosition({
    keepTransactions
  }: {
    keepTransactions: boolean;
  }) {
    const positionId = deletePositionDialog.positionId;
    if (positionId == null) return;
    deletePositionDialog.loading = true;
    try {
      // keepTransactions=true → 只删持仓、保留交易（对应旧实现的「仅删除持仓」分支）
      await deleteLedgerPosition(
        Number(ledgerId.value),
        positionId,
        keepTransactions
      );
      ElMessage.success(
        keepTransactions ? "持仓已删除，交易记录保留" : "持仓及关联交易已删除"
      );
      deletePositionDialog.visible = false;
      loadHoldings();
      // 交易列表引用的是内存缓存，必须置空才会重新拉取
      transactionsApi.value?.resetCache();
    } catch (e) {
      const err = e as { response?: { data?: { message?: string } } };
      ElMessage.error(err?.response?.data?.message || "删除失败");
    } finally {
      deletePositionDialog.loading = false;
    }
  }

  function openDeleteDialog(account: LedgerItem) {
    deletingAccount.value = account;
    deleteDialogVisible.value = true;
  }

  // 编辑账户弹窗（EditAccountDialog）保存成功后：刷新账户列表 / 概览 / 持仓
  async function onAccountUpdated() {
    const ledgerRes = await getLedgers();
    ledgers.value = ledgerRes.data ?? [];
    await loadSummary();
    await loadHoldings();
  }

  // 迁移决议面板（MigrationResolvePanel）提交成功后：清空交易缓存并刷新概览 / 持仓
  function onMigrationCommitted() {
    transactionsApi.value?.resetCache();
    loadSummary();
    loadHoldings();
  }

  // 子组件命令式打开入口（defineExpose）
  const migrateDialogRef = ref<MigrateDialogInstance | null>(null);
  const migrationPanelRef = ref<MigrationPanelInstance | null>(null);

  // 只需一行，页面全自动刷新
  usePageRefresh(handleGlobalRefresh);

  // 加载优化：概览与持仓并行拉取，减少首屏等待（loading 期间显示骨架屏，见模板）
  onMounted(async () => {
    loading.value = true;
    // 阈值控制：200ms 后仍未完成才显示骨架屏；快速请求（<200ms）不显示，避免闪屏
    skeletonTimer = setTimeout(() => {
      showSkeleton.value = true;
    }, 200);
    try {
      // 销售机构候选：编辑弹窗下拉数据源（内部兜底，失败不打断主流程）
      await loadSalesInstitutions();
      // 组合列表与概览/持仓并行：它是「所属组合」列的候选项与名称来源，
      // 晚一步不影响主数据，故不必串行等待（见 loadPortfolioContext 注释）。
      await Promise.all([
        loadSummary(),
        loadHoldings(),
        loadPortfolioContext()
      ]);
      // 货基收益依赖 summary 判定账户类型，故在 summary 就绪后再拉
      if (summaryData.value?.ledger_type === "fund")
        await loadMoneyFundIncome();
      // 修复：首屏填充 ledgers，使 accountInfo 可解析，从而显示右上角操作栏
      // （编辑/归档/删除/对账/批量迁移）。此前仅在点击这些按钮时才拉取，
      // 而按钮本身又在 v-if="accountInfo" 内，形成死锁导致操作栏永不显示。
      // 拉取失败仅影响操作栏可用性，不阻断概览/持仓等主流程，故单独兜底。
      try {
        const ledgerRes = await getLedgers(true);
        ledgers.value = ledgerRes.data ?? [];
        // 账本列表到位才算「继承态可判」：账户详情页的继承来源就是本账户的
        // `portfolio_id`，拿不到它时不能退化成「未归属」（见 useLedgerPositionPortfolio）
        markLedgersLoaded();
      } catch (error) {
        console.error(
          "获取账本列表失败，操作栏暂不可用（其余详情正常）",
          error
        );
      }
    } catch (e) {
      const err = e as { message?: string };
      ElMessage.error(err?.message || "加载失败");
    } finally {
      if (skeletonTimer) {
        clearTimeout(skeletonTimer);
        skeletonTimer = null;
      }
      showSkeleton.value = false;
      loading.value = false;
    }
  });

  return {
    ledgerId,
    ledgerIdNum,
    loading,
    showSkeleton,
    ledgers,
    portfolioList,
    salesInstitutions,
    deleteDialogVisible,
    deletingAccount,
    showEditDialog,
    drawerVisible,
    selectedPosition,
    summaryData,
    moneyFundData,
    todayPnlData,
    isCompositionLedger,
    compositionData,
    compositionColorMap,
    accountInfo,
    accountName,
    subTitle,
    getAllocColor,
    cashLedgers,
    sameTypeLedgers,
    activeTab,
    activeSearch,
    onSearchInput,
    holdingsPage,
    holdingsPageSize,
    holdingsList,
    holdingsTotal,
    loadHoldings,
    resolveHoldingPortfolio,
    reassignPosition,
    openPositionDrawer,
    loadSummary,
    refreshAfterPositionTxnChange,
    openEditDialog,
    toggleArchiveDetail,
    openDeletePositionDialog,
    closeDeletePositionDialog,
    handleDeletePosition,
    deletePositionDialog,
    openDeleteDialog,
    onAccountUpdated,
    onMigrationCommitted,
    onTabChange,
    migrateDialogRef,
    migrationPanelRef,
    bindTransactions
  };
}
