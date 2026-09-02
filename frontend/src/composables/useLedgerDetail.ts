import {
  ref,
  computed,
  onMounted,
  shallowRef,
  type Ref,
  type ComputedRef
} from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  getLedgers,
  getLedgerSummary,
  getLedgerPositions,
  deleteLedgerPosition,
  archiveLedger,
  unarchiveLedger,
  getSalesInstitutions,
  type LedgerItem,
  type SalesInstitution
} from "@/api/ledger";
import { getPortfolios, type PortfolioItem } from "@/api/portfolio";
import {
  getMoneyFundIncome,
  type MoneyFundIncomeData
} from "@/api/performance";
import { getLedgerTypeLabel } from "@/constants";
import { usePageRefresh } from "@/composables/usePageRefresh";

/** 账户概览（GET /api/ledgers/{id}/summary/） */
export interface LedgerSummaryData {
  ledger_id?: number;
  ledger_name?: string;
  ledger_type?: string;
  portfolio_name?: string | null;
  total_market_value?: number;
  position_pnl?: number;
  position_count?: number;
  cash_balance?: number | null;
  /** 类现金合计（#1137）：货基 + 逆回购 + 账户现金，口径同 XIRR EXCLUDED_ASSET_TYPES */
  cash_like_amount?: number;
  /** 中高风险投资资产 = 总市值 - 类现金（#1137） */
  investment_amount?: number;
  /** 类现金明细：货基市值 */
  money_fund_amount?: number;
  /** 类现金明细：账户现金 */
  cash_amount?: number;
  linked_liability?: number;
  type_distribution?: Record<string, number>;
}

/** 持仓行（GET /api/ledgers/{id}/positions/ 分页 items） */
export interface LedgerHoldingRow {
  id: number;
  symbol?: string;
  name?: string | null;
  asset_type?: string;
  type_label?: string;
  market_value?: number;
  pnl?: number;
  pnl_rate?: number;
  avg_price?: number;
  /** 持有时长（天），基于本轮建仓确认日 confirm_date；清仓后重买重置；无确认日时为 null（#862） */
  holding_days?: number | null;
  current_price?: number;
  allocation?: string | null;
  allocation_label?: string;
  quantity?: number;
  account_name?: string;
}

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
  isUnclassified: ComputedRef<boolean>;
  loading: Ref<boolean>;
  showSkeleton: Ref<boolean>;
  ledgers: Ref<LedgerItem[]>;
  portfolioList: Ref<PortfolioItem[]>;
  salesInstitutions: Ref<SalesInstitution[]>;
  assignMap: Ref<Record<number, number>>;
  deleteDialogVisible: Ref<boolean>;
  deletingAccount: Ref<LedgerItem | null>;
  showEditDialog: Ref<boolean>;
  drawerVisible: Ref<boolean>;
  selectedPosition: Ref<LedgerHoldingRow | null>;
  summaryData: Ref<LedgerSummaryData | null>;
  moneyFundData: Ref<MoneyFundIncomeData | null>;
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
  openPositionDrawer: (row: LedgerHoldingRow) => void;
  openEditDialog: () => Promise<void>;
  toggleArchiveDetail: (ledger: LedgerItem) => Promise<void>;
  confirmDeletePosition: (row: LedgerHoldingRow) => Promise<void>;
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
 * 交易流水 Tab 的状态与函数见 useLedgerTransactions；批量迁移残留逻辑见 usePositionMigration。
 * 共享状态（ledgers / accountInfo / salesInstitutions / ledgerId / accountName 等）统一在此持有，
 * 其余 composable 通过参数复用同一实例，避免重复声明导致状态分裂。
 */
export function useLedgerDetail(): LedgerDetailApi {
  const route = useRoute();

  const ledgerId = computed(() => route.params.id as string);
  const isUnclassified = computed(
    () => ledgerId.value === "unclassified" || !!route.query.name
  );
  const targetAccountName = computed(
    () => route.query.name as string | undefined
  );

  const loading = ref(true);
  // 骨架屏阈值控制：请求 ≤200ms 返回时直接渲染内容、跳过骨架屏，避免"闪屏"（骨架刚出现就消失）
  const showSkeleton = ref(false);
  let skeletonTimer: ReturnType<typeof setTimeout> | null = null;
  const ledgers = ref<LedgerItem[]>([]);
  const portfolioList = ref<PortfolioItem[]>([]);
  /** 基金销售机构候选（AMAC 名录，编辑账户可选关联） */
  const salesInstitutions = ref<SalesInstitution[]>([]);
  const assignMap = ref<Record<number, number>>({});
  const deleteDialogVisible = ref(false);
  const deletingAccount = ref<LedgerItem | null>(null);

  const showEditDialog = ref(false);

  const drawerVisible = ref(false);
  const selectedPosition = ref<LedgerHoldingRow | null>(null);

  // 概览数据
  const summaryData = ref<LedgerSummaryData | null>(null);

  // 货币基金收益（仅基金账户拉取）
  const moneyFundData = ref<MoneyFundIncomeData | null>(null);

  // 是否展示资产构成（仅股票 / 基金 / 信用账户有投资资产与现金类资产之分）
  const isCompositionLedger = computed(() =>
    ["stock", "fund", "e_account"].includes(
      summaryData.value?.ledger_type ?? ""
    )
  );

  // 环形图数据：投资资产 vs 现金类资产
  const compositionData = computed(() => [
    { name: "投资资产", value: summaryData.value?.investment_amount ?? 0 },
    { name: "现金类资产", value: summaryData.value?.cash_like_amount ?? 0 }
  ]);

  // 环形图配色：走 design.md 图表语义变量（禁止硬编码 hex），对齐家庭资产看板饼图取色（chart-01 起）
  const compositionColorMap = {
    投资资产: "--chart-01",
    现金类资产: "--chart-06"
  };

  async function loadMoneyFundIncome() {
    if (isUnclassified.value) return;
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

  // 持仓 Tab 数据
  const holdingsPage = ref(1);
  const holdingsPageSize = 20;
  const holdingsList = ref<LedgerHoldingRow[]>([]);
  const holdingsTotal = ref(0);
  // 名称/代码搜索（#982）：后端 LIKE 过滤，防抖后重置回第一页
  const holdingsSearch = ref("");

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
  const accountName = computed(() => {
    if (targetAccountName.value) return targetAccountName.value;
    if (isUnclassified.value) return "未归置持仓";
    return (
      accountInfo.value?.name || summaryData.value?.ledger_name || "账户详情"
    );
  });

  const subTitle = computed(() => {
    if (isUnclassified.value) return "将以下资产关联到已有账户";
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
    if (!isUnclassified.value) {
      await loadSummary();
    }
    await loadHoldings();
    // 如果当前用户正在看的是交易记录 Tab，顺便刷新交易记录
    if (activeTab.value === "transactions") {
      await transactionsApi.value?.loadTransactions();
    }
  }

  async function loadSummary() {
    try {
      const res = await getLedgerSummary(Number(ledgerId.value));
      summaryData.value = (res as { data?: LedgerSummaryData })?.data ?? {};
    } catch {
      ElMessage.error("概览加载失败");
    }
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

  // 持仓加载
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
      holdingsList.value = result?.items ?? [];
      holdingsTotal.value = result?.total ?? 0;
    } catch {
      ElMessage.error("持仓加载失败");
    }
  }

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
      portfolioList.value =
        (portfolioRes as { data?: PortfolioItem[] })?.data ?? [];
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
    } catch (e: any) {
      if (e !== "cancel" && e?.action !== "cancel") {
        ElMessage.error(e?.message || "操作失败");
      }
    }
  }

  async function confirmDeletePosition(row: LedgerHoldingRow) {
    const positionId = row.id;
    try {
      await ElMessageBox.confirm(
        `确定删除持仓「${row.name || row.symbol}」吗？可选择同时删除关联交易记录。`,
        "删除持仓",
        {
          confirmButtonText: "删除持仓及交易",
          cancelButtonText: "仅删除持仓",
          distinguishCancelAndClose: true,
          type: "warning"
        }
      );

      // ✅ 用户点击了【删除持仓及交易】
      await deleteLedgerPosition(Number(ledgerId.value), positionId, true);
      ElMessage.success("持仓及关联交易已删除");

      // 刷新持仓列表
      loadHoldings();
      // 🔥 核心修复：清除交易列表缓存，保证用户切换 Tab 后会自动拉取最新数据
      transactionsApi.value?.resetCache();
    } catch (action: unknown) {
      // ✅ 用户点击了【仅删除持仓】（ElMessageBox 取消分支返回 "cancel"）
      if (action === "cancel") {
        try {
          await deleteLedgerPosition(Number(ledgerId.value), positionId, false);
          ElMessage.success("持仓已删除，交易记录保留");

          // 刷新持仓列表
          loadHoldings();
          // 🔥 核心修复：虽然保留了交易记录，但交易列表引用的是内存缓存，强制置空以触发刷新
          transactionsApi.value?.resetCache();
        } catch (e) {
          const err = e as { response?: { data?: { message?: string } } };
          ElMessage.error(err?.response?.data?.message || "删除失败");
        }
      }
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
      if (!isUnclassified.value) {
        await Promise.all([loadSummary(), loadHoldings()]);
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
        } catch (error) {
          console.error(
            "获取账本列表失败，操作栏暂不可用（其余详情正常）",
            error
          );
        }
      } else {
        await loadHoldings();
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
    isUnclassified,
    loading,
    showSkeleton,
    ledgers,
    portfolioList,
    salesInstitutions,
    assignMap,
    deleteDialogVisible,
    deletingAccount,
    showEditDialog,
    drawerVisible,
    selectedPosition,
    summaryData,
    moneyFundData,
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
    openPositionDrawer,
    openEditDialog,
    toggleArchiveDetail,
    confirmDeletePosition,
    openDeleteDialog,
    onAccountUpdated,
    onMigrationCommitted,
    onTabChange,
    migrateDialogRef,
    migrationPanelRef,
    bindTransactions
  };
}
