import { ref, computed, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { usePageRefresh } from "@/composables/usePageRefresh";
import {
  getLedgers,
  getLedgersOverview,
  getSalesInstitutions,
  archiveLedger,
  unarchiveLedger,
  reorderLedgers,
  getFundAggregation,
  getSecuritiesAggregation,
  type SalesInstitution
} from "@/api/ledger";
import {
  getLedgerConsistency,
  type LedgerConsistencyItem
} from "@/api/reconciliation";
import Sortable from "sortablejs";
import { getPortfolios } from "@/api/portfolio";
import { getChannelCategoryLabel } from "@/constants";
import { formatDateTime } from "@/utils/date";

/**
 * 账户列表页状态单体（#980 P1-C 结构拆分）：
 * 账户数据拉取 / 分组构建 / 卡片与分组双层拖拽 / 归档与删除对话框状态收敛在这里，
 * index.vue 只做编排，两个子组件经 page prop 注入同一实例（P1-A/B 同款模式）。
 * 分组容器 DOM ref（groupsContainer）由 LedgerGroupsList 的模板绑定写入同一 Ref。
 */
export function useLedgerList() {
  const router = useRouter();

  const loading = ref(true);
  const allLedgers = ref<any[]>([]);
  const overviewData = ref<{
    net_worth: number;
    liability_total: number;
    groups: any[];
  }>({
    net_worth: 0,
    liability_total: 0,
    groups: []
  });
  const lastUpdate = ref("");

  /** 场外基金（含E账户）聚合总市值（分，整数）；独立获取，失败不影响主账户列表 */
  const fundTotalCents = ref(0);
  const fundTotalYuan = computed(() => fundTotalCents.value / 100);

  /** 场内证券（股票/ETF/可转债）聚合总市值（分，整数）；独立获取，失败不影响主账户列表 */
  const securitiesTotalCents = ref(0);
  const securitiesTotalYuan = computed(() => securitiesTotalCents.value / 100);

  const showCreateDialog = ref(false);
  /** 创建弹窗初始渠道分组：顶部「新增账户」默认 bank；分组幽灵按钮预置对应渠道分组 */
  const initialCreateType = ref("bank");
  /** 基金销售机构候选（AMAC 名录，创建账户可选关联） */
  const salesInstitutions = ref<SalesInstitution[]>([]);

  const cashLedgers = computed(() =>
    allLedgers.value.filter((l: any) => l.ledger_type === "bank")
  );
  /** 已归档账户数量（用于工具栏徽标），数据来自全量列表 */
  const archivedCount = computed(
    () => allLedgersRaw.value.filter((l: any) => l.is_active === false).length
  );
  const portfolioList = ref<any[]>([]);
  const deleteDialogVisible = ref(false);
  const deletingAccount = ref<any>(null);
  /** 是否在列表显示已归档账户（默认隐藏，归档数据仍计入顶部净资产/配置图） */
  const showArchived = ref(false);
  /** 全量账户（含已归档），用于按开关过滤展示 + 统计归档数 */
  const allLedgersRaw = ref<any[]>([]);

  /** 各账户持仓快照一致性（#1133 §4 温柔提醒数据源）：拉一次后按 ledger 聚合待核对数 */
  const ledgerConsistencyItems = ref<LedgerConsistencyItem[]>([]);
  const staleCountByLedger = computed<Record<number, number>>(() =>
    ledgerConsistencyItems.value.reduce(
      (acc, it) => {
        if (it.ledger_id != null)
          acc[it.ledger_id] = (acc[it.ledger_id] ?? 0) + 1;
        return acc;
      },
      {} as Record<number, number>
    )
  );

  // 总资产（从 overview groups 汇总）
  const totalAssets = computed(
    () =>
      overviewData.value?.groups?.reduce(
        (sum: number, g: any) => sum + (g.total || 0),
        0
      ) ?? 0
  );

  // 负债率偏高警示：仅当负债 > 0 且超过总资产一半时显示（负债为 0 时不渲染刺眼文案）
  const showHighLiabilityWarning = computed(
    () =>
      overviewData.value.liability_total > 0 &&
      overviewData.value.liability_total > totalAssets.value * 0.5
  );

  // 负债率：可计算时显示百分比（负债/总资产），无负债或不可计算时显示 --
  const liabilityRate = computed(() => {
    if (overviewData.value.liability_total <= 0 || totalAssets.value <= 0) {
      return "--";
    }
    return `${((overviewData.value.liability_total / totalAssets.value) * 100).toFixed(1)}%`;
  });

  // ── 资产配置环形图逻辑已拆分至 components/LedgerAllocationCard.vue（#984）──

  // 已删除账户的持仓信息（来自 overview）
  const orphanGroup = computed(() =>
    overviewData.value?.groups?.find((g: any) => g.type === "deleted")
  );

  // 分组展示（按渠道分组 channel_category，组内排序）：手动排序序号优先，回退按持仓金额降序（#1083）
  // 旧数据可能无 channel_category，按 legacy ledger_type 映射兜底到对应渠道分组。
  const LEGACY_TYPE_TO_CHANNEL: Record<string, string> = {
    bank: "bank",
    stock: "securities",
    fund: "fund_platform",
    property: "other"
  };
  function channelOf(ledger: any): string {
    if (ledger.channel_category) return ledger.channel_category;
    return LEGACY_TYPE_TO_CHANNEL[ledger.ledger_type] || "other";
  }

  function buildGroups(ledgers: any[]) {
    const groups: Record<string, any> = {};
    for (const ledger of ledgers) {
      const type = channelOf(ledger);
      if (!groups[type]) {
        groups[type] = {
          type,
          label: getChannelCategoryLabel(type),
          total: 0,
          count: 0,
          ledgers: [] as any[]
        };
      }
      groups[type].count++;
      groups[type].total += ledger.total_market_value || 0;
      groups[type].ledgers.push(ledger);
    }

    // 分组顺序来自本地偏好（groupOrder），默认 银行/证券/基金/保险/期货/其他；
    // 仅保留实际有账户的分组（空分组不渲染）。
    //
    // 修复（账户列表白屏 / 账户不显示）：
    // 1) groupOrder 是 string[]，filter 返回的是分组 **key 字符串**，必须 map 回
    //    groups 对象——否则下方 g.ledgers.sort() 会对字符串取属性，抛
    //    "Cannot read properties of undefined (reading 'sort')" 导致整页渲染中断。
    // 2) groupOrder 未涵盖的分组（如新增渠道、旧数据兜底出的类型）追加到末尾，
    //    避免这些账户被静默丢弃而"凭空消失"。
    const orderedTypes = groupOrder.value.filter(type => groups[type]);
    const restTypes = Object.keys(groups).filter(
      type => !orderedTypes.includes(type)
    );
    const result = [...orderedTypes, ...restTypes].map(
      type => groups[type]
    ) as any[];

    // 未归置持仓不再作为分组卡片进入网格（2026-08 改版），统一由顶部警示 banner 承接
    // 组内排序：已手动排序（display_order 非 null）的卡片按 display_order 升序排在前面，
    // 其余（null）回退到「按持仓金额降序」，默认即金额大的靠前。
    for (const g of result) {
      // 防御：分组结构异常（无 ledgers 数组）时跳过，避免一处脏数据让整页白屏
      if (!Array.isArray(g?.ledgers)) continue;
      g.ledgers.sort((a: any, b: any) => {
        const da = a.display_order ?? Infinity;
        const db = b.display_order ?? Infinity;
        if (da !== db) return da - db;
        return (b.total_market_value || 0) - (a.total_market_value || 0);
      });
    }
    return result;
  }

  // 实际渲染用的分组（可被拖拽直接重排：拖拽时修改该分组 ledgers 数组并落库）
  const displayedGroups = ref<any[]>([]);

  // ── 分组顺序（纯视图偏好，存 localStorage，不落库；与组内卡片排序分层）──
  const GROUP_ORDER_KEY = "fundmate:ledgerGroupOrder:v1";
  const DEFAULT_GROUP_ORDER = [
    "bank",
    "securities",
    "fund_platform",
    "insurance",
    "futures",
    "other"
  ];
  function loadGroupOrder(): string[] {
    try {
      const raw = localStorage.getItem(GROUP_ORDER_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.every(t => typeof t === "string")) {
          const stored = parsed.filter(t => DEFAULT_GROUP_ORDER.includes(t));
          const missing = DEFAULT_GROUP_ORDER.filter(t => !stored.includes(t));
          return [...stored, ...missing];
        }
      }
    } catch {
      /* 解析失败时回退默认顺序 */
    }
    return [...DEFAULT_GROUP_ORDER];
  }
  function saveGroupOrder(order: string[]) {
    try {
      localStorage.setItem(GROUP_ORDER_KEY, JSON.stringify(order));
    } catch {
      /* 隐私模式等场景忽略写入失败 */
    }
  }
  const groupOrder = ref<string[]>(loadGroupOrder());

  // 分组整体拖拽（与卡片拖拽是两套独立 Sortable，handle 互不触发）
  const groupsContainer = ref<HTMLElement | null>(null);
  // 拖拽中的分组类型：用于高亮当前被拖的分组，强化「正在重排整段」的反馈
  const draggingGroupType = ref<string | null>(null);
  let groupSortable: any = null;
  function destroyGroupSortable() {
    if (groupSortable) {
      groupSortable.destroy();
      groupSortable = null;
    }
  }
  function initGroupSortable() {
    destroyGroupSortable();
    if (!groupsContainer.value) return;
    groupSortable = Sortable.create(groupsContainer.value, {
      animation: 180,
      handle: ".group-drag-handle",
      ghostClass: "ledger-group--ghost",
      onStart: (evt: any) => {
        const moved = displayedGroups.value[evt.oldIndex];
        draggingGroupType.value = moved?.type ?? null;
      },
      onEnd: (evt: any) => {
        const { oldIndex, newIndex } = evt;
        draggingGroupType.value = null;
        if (oldIndex == null || newIndex == null || oldIndex === newIndex)
          return;
        const arr = displayedGroups.value;
        const [moved] = arr.splice(oldIndex, 1);
        if (!moved) return;
        arr.splice(newIndex, 0, moved);
        const order = arr.map(g => g.type);
        groupOrder.value = order;
        saveGroupOrder(order);
      }
    });
  }

  // ── 拖拽排序（仅限同类型组内，#1083）──
  const sortables: Record<string, any> = {};
  function destroySortables() {
    Object.values(sortables).forEach((s: any) => s.destroy());
    for (const k of Object.keys(sortables)) delete sortables[k];
  }
  function initSortables() {
    destroySortables();
    for (const g of displayedGroups.value) {
      const el = document.querySelector(
        `.ledger-grid[data-ledger-type="${g.type}"]`
      ) as HTMLElement | null;
      if (!el) continue;
      sortables[g.type] = Sortable.create(el, {
        animation: 180,
        handle: ".drag-handle",
        ghostClass: "ledger-card--ghost",
        chosenClass: "ledger-card--chosen",
        onEnd: (evt: any) => onLedgerDragEnd(g.type, evt)
      });
    }
  }
  function onLedgerDragEnd(type: string, evt: any) {
    const group = displayedGroups.value.find(g => g.type === type);
    if (!group) return;
    const { oldIndex, newIndex } = evt;
    if (oldIndex == null || newIndex == null || oldIndex === newIndex) return;
    const arr = group.ledgers;
    const [moved] = arr.splice(oldIndex, 1);
    if (!moved) return;
    arr.splice(newIndex, 0, moved);
    const orderedIds = arr.map((l: any) => l.id);
    // 落库按真实 ledger_type 排序（channel_category 由 ledger_type 派生，组内 ledger_type 一致）
    const ledgerType = group.ledgers[0]?.ledger_type ?? type;
    // 乐观更新已在 UI 生效；落库失败则回填并重拉，保证最终一致
    reorderLedgers(ledgerType, orderedIds).catch(() => {
      ElMessage.error("排序保存失败，已恢复");
      fetchData();
    });
  }

  function openCreateDialog(channelCategory?: string) {
    // 显式传 undefined 时回退默认 bank，避免点击事件对象被误当类型参数
    initialCreateType.value =
      channelCategory && typeof channelCategory === "string"
        ? channelCategory
        : "bank";
    showCreateDialog.value = true;
  }

  function openDeleteDialog(account: any) {
    deletingAccount.value = account;
    deleteDialogVisible.value = true;
  }

  /** 归档/激活切换。归档有数据账户是安全的（保留全部数据、仅隐藏），但给一次确认。 */
  async function onToggleArchive(ledger: any) {
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
      fetchData();
    } catch (e: any) {
      if (e !== "cancel" && e?.action !== "cancel") {
        ElMessage.error(e?.message || "操作失败");
      }
    }
  }

  function goToDetail(ledger: any) {
    router.push({ name: "LedgerDetail", params: { id: ledger.id } });
  }

  /**
   * 下钻到场外基金（含E账户）聚合视图。
   * #1133 路由归并：目标由隐藏页 /asset/fund-aggregation 收敛为正式页 /funds（AssetFunds），
   * 与「资产总览 → 产品类型 → 基金」的下钻目标合为同一个页面，消除重复路由。
   */
  function goToFundAggregation() {
    router.push({ name: "AssetFunds" });
  }

  /**
   * 下钻到场内证券（股票/ETF/可转债）聚合视图。
   * #1133 路由归并：目标收敛为正式页 /stocks（AssetStocks），同上。
   */
  function goToSecuritiesAggregation() {
    router.push({ name: "AssetStocks" });
  }

  async function fetchData() {
    loading.value = true;
    try {
      const [ledgersRes, overviewRes, portfolioRes, instRes] =
        await Promise.all([
          getLedgers(true),
          getLedgersOverview(),
          getPortfolios(),
          getSalesInstitutions()
        ]);
      allLedgersRaw.value = (ledgersRes as any)?.data ?? [];
      // 按「显示已归档」开关过滤展示列表（归档数据始终计入顶部净资产/配置图）
      allLedgers.value = showArchived.value
        ? allLedgersRaw.value
        : allLedgersRaw.value.filter((l: any) => l.is_active !== false);
      overviewData.value = (overviewRes as any)?.data ?? {
        net_worth: 0,
        liability_total: 0,
        groups: []
      };
      portfolioList.value = (portfolioRes as any)?.data ?? [];
      salesInstitutions.value =
        (instRes as { data?: SalesInstitution[] })?.data ?? [];
      // 快照一致性：独立请求，失败静默兜底不阻塞主列表（#ai-review）
      getLedgerConsistency()
        .then(res => {
          ledgerConsistencyItems.value = res.data?.items ?? [];
        })
        .catch(() => {
          ledgerConsistencyItems.value = [];
        });
      // 重新分组并构建可拖拽的展示结构（含「金额降序 / 手动序号」排序规则）
      displayedGroups.value = buildGroups(allLedgers.value);
      // 统一走公共格式化：YYYY-MM-DD HH:mm（不带秒），避免斜线/时分秒混用
      lastUpdate.value = formatDateTime(new Date());
      nextTick(() => {
        initSortables();
        initGroupSortable();
      });
    } catch (e: any) {
      ElMessage.error(e?.message || "加载失败");
    } finally {
      loading.value = false;
    }
    // 独立获取场外基金（含E账户）聚合总市值：与账户列表解耦，失败静默兜底不阻塞主列表
    fetchFundTotal();
    // 独立获取场内证券（股票/ETF/可转债）聚合总市值：同范式，失败静默兜底不阻塞主列表
    fetchSecuritiesTotal();
  }

  /** 独立获取场外基金聚合总市值（GET /api/ledgers/fund-aggregation/）。
   *  汇总值与维度无关（始终为全量场外基金市值），故用默认 product 维度取一次即可。 */
  async function fetchFundTotal() {
    try {
      const res = await getFundAggregation({ dimension: "product" });
      fundTotalCents.value = res.data?.total_market_value_cents ?? 0;
    } catch {
      fundTotalCents.value = 0;
    }
  }

  /** 独立获取场内证券聚合总市值（GET /api/ledgers/securities-aggregation/）。
   *  汇总值与维度无关（始终为全量场内证券市值），故用默认 product 维度取一次即可。
   *  与账户列表解耦、失败静默兜底不阻塞主列表（同 fetchFundTotal 范式）。 */
  async function fetchSecuritiesTotal() {
    try {
      const res = await getSecuritiesAggregation({ dimension: "product" });
      securitiesTotalCents.value = res.data?.total_market_value_cents ?? 0;
    } catch {
      securitiesTotalCents.value = 0;
    }
  }

  // 只需一行，列表全自动刷新
  usePageRefresh(() => {
    fetchData();
  });

  onMounted(() => {
    fetchData();
  });

  return {
    loading,
    allLedgers,
    overviewData,
    lastUpdate,
    fundTotalYuan,
    securitiesTotalYuan,
    showCreateDialog,
    initialCreateType,
    salesInstitutions,
    cashLedgers,
    archivedCount,
    portfolioList,
    deleteDialogVisible,
    deletingAccount,
    showArchived,
    staleCountByLedger,
    totalAssets,
    showHighLiabilityWarning,
    liabilityRate,
    orphanGroup,
    displayedGroups,
    groupsContainer,
    draggingGroupType,
    getChannelCategoryLabel,
    openCreateDialog,
    openDeleteDialog,
    onToggleArchive,
    goToDetail,
    goToFundAggregation,
    goToSecuritiesAggregation,
    fetchData
  };
}
