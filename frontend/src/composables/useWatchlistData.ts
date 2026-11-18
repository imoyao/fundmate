import { ref, computed, watch } from "vue";
import { storeToRefs } from "pinia";
import { ElMessage } from "element-plus";
import { getWatchlistItems, type WatchlistItem } from "@/api/watchlist";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import { useWatchlistRowActions } from "@/composables/watchlist/useWatchlistRowActions";
import {
  sortRowsForClient,
  type ClientSortKey,
  type ClientSortOrder
} from "@/views/asset/watchlist/clientSort";
import type { SortMetric } from "@/views/asset/watchlist/sortMetric";
import {
  PAGE_SIZE_OPTIONS,
  useWatchlistPrefsStore
} from "@/store/modules/watchlistPrefs";

/**
 * 每页条数与复合列排序口径已下沉到 `store/modules/watchlistPrefs`（#2922）：
 * 二者是**跨挂载点共享**的本地视图偏好（自选页表格 + 设置抽屉同一份），
 * 原先以模块级单例住在本文件顶层，属于「状态归属说不清」的技术债。
 * 此处 re-export 保持既有导入路径可用（`useWatchlistData` 的调用方无需改）。
 */
export { PAGE_SIZE_OPTIONS };

/**
 * 自选列表「数据 + 分页 + 筛选 + 行操作 + 批量」编排逻辑（从 watchlist/index.vue 抽离，2026-08-20）。
 *
 * 设计边界：
 * - 分组 / 标签筛选的状态各自收敛在 useWatchlistGroups / useWatchlistTags，本 composable 仅消费，
 *   不重复定义域；拼 fetchParams 时复用两者的派生态（activeGroup / selectedFilterTagIds 等）。
 * - 顶部工具栏（搜索框、批量模式、视图 segmented）由 useWatchlistToolbar 收口；其状态经构造参数注入。
 * - 弹窗开关（添加/OCR/管理/标签编辑）仍留在页面模板，本 composable 只暴露「刷新」等副作用入口。
 *
 * @param groups useWatchlistGroups() 实例（提供 activeGroup / allGroups / currentIsCustom / activeCustomGroupId）
 * @param tags   useWatchlistTags() 实例（提供 selectedFilterTagIds / resetTagFilter）
 * @param toolbar 顶部工具栏状态（搜索关键字 / 视图 segmented / 批量模式），见 useWatchlistToolbar
 */
export interface WatchlistToolbarState {
  searchKeyword: ReturnType<typeof ref<string>>;
  currentView: ReturnType<typeof ref<string>>;
  /** 资产类型多选筛选（「类型」弹层；空数组 = 不过滤） */
  selectedAssetTypes: ReturnType<typeof ref<string[]>>;
  batchMode: ReturnType<typeof ref<boolean>>;
  selectedItems: ReturnType<typeof ref<WatchlistItem[]>>;
  batchMoveGroupId: ReturnType<typeof ref<number | undefined>>;
}

export function useWatchlistData(
  groups: ReturnType<typeof useWatchlistGroups>,
  tags: ReturnType<typeof useWatchlistTags>,
  toolbar: WatchlistToolbarState
) {
  const { activeGroup, allGroups, activeCustomGroupId, currentIsCustom } =
    groups;
  const { selectedFilterTagIds } = tags;
  const {
    searchKeyword,
    currentView,
    selectedAssetTypes,
    batchMode,
    selectedItems,
    batchMoveGroupId
  } = toolbar;

  // 跨挂载点共享的本地偏好（每页条数 / 复合列口径）由 store 持有（#2922）；
  // 本 composable 只用它的 ref 参与 watch 与模板，值本身不进本文件。
  const prefs = useWatchlistPrefsStore();
  const { pageSize, sortMetrics } = storeToRefs(prefs);

  // 口径偏好首屏前恢复（幂等；失败静默回默认「金额」）
  void prefs.loadSortMetrics();

  const loading = ref(false);
  const items = ref<WatchlistItem[]>([]);
  // 全量过滤结果（忽略分页）：供实时估值汇总条使用（#1245）。
  // 汇总（总市值/总成本/总盈亏）必须基于整组而非当前页，否则翻页时数据会跳变。
  const allItems = ref<WatchlistItem[]>([]);
  const currentPage = ref(1);
  const totalItems = ref(0);

  // 用户列内排序状态（#991）：空串表示未排序（后端走默认置顶+更新时间）
  const sortBy = ref("");
  const sortOrder = ref<"asc" | "desc">("asc");

  /**
   * 整组客户端排序（2026-10-30）：非空 = 当前排序由前端对**全量** allItems 算，
   * 后端 `sort_by` 不参与。
   *
   * 为什么这两列不能走后端：后端 `current_price` / `change_pct` 是**上一交易日收盘**
   * 算出来的（job 每天 17:30 跑），按它排等于「按昨天的涨跌幅排」，与列里显示的今日
   * 实时值不是同一个数。完整推导见 `views/asset/watchlist/clientSort.ts`。
   */
  const clientSortKey = ref<"" | ClientSortKey>("");
  const clientSortOrder = ref<ClientSortOrder>("desc");
  const clientSortValueOf = ref<((row: WatchlistItem) => number | null) | null>(
    null
  );

  /** 拼后端请求参数：分页 + 分组过滤 + 标签筛选 + 场内/场外 + 搜索。 */
  const fetchParams = computed(() => {
    const params: Record<string, string | number | boolean> = {
      page: currentPage.value,
      per_page: pageSize.value
    };
    if (selectedFilterTagIds.value.length > 0) {
      params.tag_ids = selectedFilterTagIds.value.join(",");
    }
    const groupKey = activeGroup.value;
    if (groupKey.startsWith("custom_")) {
      const groupId = activeCustomGroupId.value;
      if (groupId) params.group_id = groupId;
    } else {
      // 系统分组过滤已随 useWatchlistGroups 收敛到 allGroups（其 filter 由 getSystemFilter 填充），直接复用
      const group = allGroups.value.find(g => g.key === groupKey);
      if (group && group.filter) {
        for (const [k, rawV] of Object.entries(group.filter)) {
          const v = rawV as string | number | boolean;
          params[k === "cleared" ? "status" : k] =
            k === "cleared" ? "cleared" : v;
        }
      }
    }
    // venue（场内/场外）过滤：2026-09-12 主界面已移除场所切换按钮，currentView 恒为 'all'，
    // 此分支实际不再命中（全部显示）。保留逻辑以兼容后续如需在「筛选」弹层内加回 venue 维度。
    if (currentView.value === "exchange") params.venue = "EXCHANGE";
    else if (currentView.value === "otc") params.venue = "OTC";
    // 资产类型多选（「类型」弹层）：逗号分隔小写枚举，后端 lower 后 in_ 匹配
    if (selectedAssetTypes.value.length > 0) {
      params.asset_types = selectedAssetTypes.value.join(",");
    }
    if (searchKeyword.value) params.q = searchKeyword.value;
    // 用户列内排序（#991）：仅白名单字段由后端校验，跨页排序一致。
    // 客户端整组排序期间不传 sort_by：后端只能按 T-1 快照排（见 clientSortKey 注释），
    // 传了反而让「拉全量的那一份」带上一层无关的服务端顺序。
    if (sortBy.value && !clientSortKey.value) {
      params.sort_by = sortBy.value;
      params.sort_order = sortOrder.value;
    }
    return params;
  });

  /**
   * 全量结果最多翻几页（后端 per_page 限幅 200）。
   *
   * 4 页 = 800 行，个人自选的规模远小于此。上限存在的原因：`fields=lite` 的全量拉取
   * 本来只为汇总条与客户端排序服务，真到上千行时应改为「后端排序 + 服务端分页」，
   * 而不是无限翻页把浏览器拖死（那时前端拿不到实时价的问题也会变成次要问题）。
   */
  const ALL_ITEMS_MAX_PAGES = 4;

  /** 拉全量结果（`fields=lite`：不含可转债条款/基金回撤等展示字段，但**含**
   *  prev_close / holding_quantity / current_price——客户端排序与汇总条都靠这三样）。 */
  async function fetchAllItems(
    base: Record<string, string | number | boolean>
  ): Promise<WatchlistItem[]> {
    const perPage = 200;
    const rows: WatchlistItem[] = [];
    for (let page = 1; page <= ALL_ITEMS_MAX_PAGES; page += 1) {
      const res = await getWatchlistItems({
        ...base,
        page,
        per_page: perPage,
        fields: "lite"
      });
      const batch = res.data ?? [];
      rows.push(...batch);
      const total = res.total ?? rows.length;
      if (batch.length < perPage || rows.length >= total) break;
    }
    return rows;
  }

  /** 拉取列表（分页切片由后端完成，前端只消费 data/total）。
   * @param refreshAll 是否顺带刷新全量结果 allItems（供估值汇总条）。
   *        筛选/排序/搜索/分组变化时应传 true；纯翻页传 false（汇总保持稳定）。
   *        全量结果用 fields=lite 拉取（必要时循环翻页，见 fetchAllItems）。
   */
  async function fetchData(refreshAll = true) {
    // 客户端整组排序期间，翻页是纯本地切片（见下面的 watch），不请求后端——
    // 否则会把已排好的本地顺序覆盖回服务端顺序（「翻页后排序失效」的典型症状）。
    if (!refreshAll && clientSortKey.value) return;
    loading.value = true;
    try {
      if (refreshAll) {
        if (clientSortKey.value) {
          // 整组排序只认全量这一份：当前页那份会被本地切片覆盖，不必发
          allItems.value = await fetchAllItems(fetchParams.value);
          totalItems.value = allItems.value.length;
        } else {
          const [pageRes, all] = await Promise.all([
            getWatchlistItems(fetchParams.value),
            fetchAllItems(fetchParams.value)
          ]);
          items.value = pageRes.data ?? [];
          totalItems.value = pageRes.total ?? items.value.length;
          allItems.value = all;
        }
      } else {
        const res = await getWatchlistItems(fetchParams.value);
        items.value = res.data ?? [];
        totalItems.value = res.total ?? items.value.length;
      }
    } catch (e) {
      ElMessage.error("获取自选列表失败");
      console.error("获取自选列表错误：", e);
    } finally {
      loading.value = false;
    }
  }

  /**
   * 客户端整组排序的全量结果（null = 未启用）。
   *
   * 用 computed 而不是「排序函数」：`valueOf` 的闭包会读实时行情（`realtime.items`），
   * 30s 一次的 tick 到达时它必须**自动重排**——普通函数只在调用时算一次，
   * 排完就停在旧价上，看起来又是「顺序乱」。
   */
  const clientSortedItems = computed(() => {
    const valueOf = clientSortValueOf.value;
    if (!clientSortKey.value || !valueOf) return null;
    return sortRowsForClient(allItems.value, {
      order: clientSortOrder.value,
      valueOf
    });
  });

  /** 本地分页：把整组排序结果切到当前页（只在客户端排序启用时生效） */
  function applyClientSlice() {
    const sorted = clientSortedItems.value;
    if (!sorted) return;
    totalItems.value = sorted.length;
    const maxPage = Math.max(1, Math.ceil(sorted.length / pageSize.value));
    if (currentPage.value > maxPage) {
      // 越界页（筛选变窄 / 条数变小）回到末页；写 currentPage 会再触发本 watch 一次
      currentPage.value = maxPage;
      return;
    }
    const start = (currentPage.value - 1) * pageSize.value;
    items.value = sorted.slice(start, start + pageSize.value);
  }

  watch([clientSortedItems, currentPage, pageSize], applyClientSlice, {
    immediate: true
  });

  // ─────────────────────────────────────────────
  // 排序 / 分页切换辅助
  // ─────────────────────────────────────────────

  /**
   * 客户端整组排序（当日盈亏 / 最新价）：交给 data 层统一算，表头只报「排什么、怎么排」。
   *
   * @param key     排序的列（名单只在 `clientSort.ts` 的 `CLIENT_SORT_KEYS` 维护）
   * @param order   升/降
   * @param valueOf 取值函数（可以读实时行情；day_pnl 还按口径选金额或涨幅）
   */
  function setClientSort(
    key: ClientSortKey,
    order: ClientSortOrder,
    valueOf: (row: WatchlistItem) => number | null
  ) {
    clientSortKey.value = key;
    clientSortOrder.value = order;
    clientSortValueOf.value = valueOf;
    // 服务端排序同时清掉：两套顺序叠在一起时，谁生效取决于「有没有请求」，无法推理
    sortBy.value = "";
    currentPage.value = 1;
  }

  /** 退出客户端整组排序（切到服务端可排的列 / 取消排序时） */
  function clearClientSort() {
    clientSortKey.value = "";
    clientSortValueOf.value = null;
  }

  /**
   * 表头排序（#991）：列已切 sortable="custom"，EP 不做页内排序，
   * 由本函数捕获排向后端（sort_by/sort_order），保证跨页一致。
   * EP 取消排序时 order 为 null → 清空排序回默认（置顶+更新时间）。
   */
  function handleSortChange({
    prop,
    order
  }: {
    prop?: string | number;
    order: "ascending" | "descending" | null;
  }) {
    // 服务端排序接管：必须先退出客户端模式，否则 fetchParams 不传 sort_by、
    // 而本地切片又会把返回的页覆盖掉 —— 两条路径互相抹掉对方的结果。
    clearClientSort();
    if (order && prop) {
      sortBy.value = String(prop);
      sortOrder.value = order === "descending" ? "desc" : "asc";
    } else {
      sortBy.value = "";
    }
    currentPage.value = 1;
    fetchData();
  }
  /** 顶部视图 segmented（全部/场内/场外）切换：重置分页并刷新 */
  function handleViewChange() {
    currentPage.value = 1;
    fetchData();
  }

  /**
   * 首屏前加载本地每页条数偏好（#1335），确保第一次 fetch 即使用已记忆的档位。
   * 幂等由 store 内部保证（记忆化的加载 Promise），此处只做转发。
   */
  function initPageSize(): Promise<void> {
    return prefs.initPageSize();
  }

  /** 切换每页条数（#1335）：记忆选择 → 回到第一页 → 重新拉取。
   *  档位归一（越界回退默认、拒绝重复档位）在 store 里判；此处只负责「变了才刷新」。 */
  function setPageSize(size: number) {
    if (!prefs.changePageSize(size)) return;
    currentPage.value = 1;
    fetchData();
  }

  /** 取某列的当前口径（转发 store；未存过 → 金额，与列主行一致） */
  function sortMetricOf(key: string): SortMetric {
    return prefs.sortMetricOf(key);
  }

  /** 切某列口径（转发 store；持久化与引用替换在 store 内完成） */
  function setSortMetric(key: string, metric: SortMetric): void {
    prefs.setSortMetric(key, metric);
  }

  /** 搜索防抖：输入 300ms 后重置分页并刷新 */
  let searchTimer: number | undefined;
  function debounceSearch() {
    clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      currentPage.value = 1;
      fetchData();
    }, 300);
  }

  /** 批量删除 / 批量移动后统一刷新 */
  function refresh() {
    fetchData();
  }

  /**
   * 标签筛选生效即回到第一页并刷新（替代 useWatchlistTags 的 refresh 回调，避免 data↔tags 循环依赖）。
   * 分组切换 / 视图切换 / 搜索防抖已有各自的刷新路径，此处只接管标签筛选。
   */
  watch(selectedFilterTagIds, () => {
    currentPage.value = 1;
    fetchData();
  });

  // ─────────────────────────────────────────────
  // 行内操作（置顶 / 特别关注 / 移除）
  // ─────────────────────────────────────────────

  /**
   * 行内与批量操作已下沉到 `watchlist/useWatchlistRowActions`（#2931，D88）：
   * 子域**没有** `fetchData`，只返回「是否已写库」信号；刷新一律由本文件发起
   * ⇒ 刷新出口唯一，不会出现「操作自己刷一次 + 别处又刷一次」。下面这些同名
   * wrapper 就是那唯一出口（页面与 `useWatchlistTable` 的接线零改动）。
   */
  const rowActions = useWatchlistRowActions(
    { activeCustomGroupId, currentIsCustom },
    { batchMode, selectedItems, batchMoveGroupId }
  );

  /** 置顶 / 取消置顶 */
  async function handleTogglePin(row: WatchlistItem) {
    if (await rowActions.togglePin(row)) fetchData();
  }

  /** 特别关注 / 取消特别关注 */
  async function handleToggleFavorite(row: WatchlistItem) {
    if (await rowActions.toggleFavorite(row)) fetchData();
  }

  const { confirmRemove, removingItem, removeScope, removeDialogVisible } =
    rowActions;

  /** 执行移除（弹窗确认后） */
  async function executeRemove() {
    if (await rowActions.executeRemove()) fetchData();
  }

  /** 行内标签编辑：无自选记录（id 为 null，如草稿态/聚合虚拟行）给出提示而非静默无反应；
     打开弹窗由页面负责（暴露 editingItem 与开关） */
  const editingItem = ref<WatchlistItem | null>(null);
  const showTagEditor = ref(false);
  function openTagEditor(row: WatchlistItem) {
    if (row.id == null) {
      ElMessage.warning(
        "该自选记录缺少主键，暂无法编辑标签，请刷新或重新添加自选"
      );
      return;
    }
    editingItem.value = row;
    showTagEditor.value = true;
  }

  // ─────────────────────────────────────────────
  // 备注编辑（#1285）：与标签编辑共用「打开弹窗由页面负责」的模式
  const editingNotesItem = ref<WatchlistItem | null>(null);
  const showNotesEditor = ref(false);
  function openNotesEditor(row: WatchlistItem) {
    if (row.id == null) {
      ElMessage.warning(
        "该自选记录缺少主键，暂无法编辑备注，请刷新或重新添加自选"
      );
      return;
    }
    editingNotesItem.value = row;
    showNotesEditor.value = true;
  }

  // ─────────────────────────────────────────────
  // 批量操作（写库与批量态收尾在子域，刷新同样只在这里发起）
  // ─────────────────────────────────────────────

  const { handleSelectionChange } = rowActions;

  async function handleBatchDelete() {
    if (await rowActions.batchDelete()) fetchData();
  }

  const handleBatchMoveToGroup = async (groupId: number | null | undefined) => {
    if (await rowActions.batchMoveToGroup(groupId)) fetchData();
  };

  /** 导出：沿用当前筛选条件打开后端导出端点 */
  function exportData() {
    try {
      const params = new URLSearchParams(
        Object.entries(fetchParams.value).map(([k, v]) => [k, String(v)])
      ).toString();
      window.open(`/api/watchlist/items/export/?${params}`, "_blank");
    } catch (e) {
      ElMessage.error("导出失败");
      console.error("导出错误：", e);
    }
  }

  /** 重置全部筛选（搜索/分组/视图/标签/类型），回弹到「持仓」默认态 */
  function resetFilters() {
    searchKeyword.value = "";
    groups.resetActiveGroup();
    currentView.value = "all";
    selectedAssetTypes.value = [];
    tags.resetTagFilter();
  }

  /**
   * 「清除筛选」一键快捷（#2199 ⑥）：清空类型 + 标签，分组切回系统「全部」
   * （key 与 useWatchlistGroups.fetchGroups 的回退值同源，是「全部」的真实 key；
   * 不用 resetActiveGroup——它回的是 holding「持仓」不是「全部」）。
   * 搜索词不清：搜索框用户可见、可自行清，不在本按钮职责内。
   *
   * 刷新路径按「谁有 watch 兜底」分流，保证每个场景恰好一次请求：
   * - 标签由非空清空 → 本文件 watch(selectedFilterTagIds)（约 255 行）兜底刷新；
   * - 分组从非「全部」切回 → index.vue watch(activeGroup)（约 251 行）兜底刷新；
   * - 两者都不触发（分组本就是「全部」、标签本就空、只清了类型）→ 显式刷新：
   *   程序化改 selectedAssetTypes 没有任何 watch 监听，是唯一无人兜底的路径，
   *   必须显式 currentPage=1 + fetchData()（#2199 用户实测的「条件残留」即此场景）。
   * 不复用 resetFilters：它回 holding 默认态、清搜索词、且不触发 fetch，语义与
   * 「清除筛选」均不符（该函数目前无任何消费方，勿据它接线）。
   */
  function clearAllFilters() {
    const hadTags = selectedFilterTagIds.value.length > 0;
    // 只有已偏离「全部」才需要切回；已在「全部」时不写入，避免空触发分组 watch
    const groupChanged = activeGroup.value !== "all";
    selectedAssetTypes.value = [];
    if (hadTags) tags.resetTagFilter();
    if (groupChanged) activeGroup.value = "all";
    // 无人兜底的场景补显式刷新；其余场景交给各自 watch（与用户手动改筛选同一刷新路径）
    if (!hadTags && !groupChanged) {
      currentPage.value = 1;
      fetchData();
    }
  }

  return {
    // 分页状态
    loading,
    items,
    allItems,
    currentPage,
    pageSize,
    totalItems,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    initPageSize,
    setPageSize,
    fetchParams,
    fetchData,
    handleSortChange,
    // 客户端整组排序（当日盈亏 / 最新价，2026-10-30）：由 useWatchlistTable 的表头分发调用
    setClientSort,
    clearClientSort,
    // 复合列的排序口径（按列 key 记忆：当日盈亏 / 持仓市值 / 持仓收益）：
    // 表头徽标常驻显示 + 点击切换，本地记忆（见 sortMetric.ts / useWatchlistTable）
    sortMetrics,
    sortMetricOf,
    setSortMetric,
    handleViewChange,
    debounceSearch,
    refresh,
    // 行内操作
    handleTogglePin,
    handleToggleFavorite,
    confirmRemove,
    executeRemove,
    removingItem,
    removeScope,
    removeDialogVisible,
    // 标签编辑
    editingItem,
    showTagEditor,
    openTagEditor,
    // 备注编辑
    editingNotesItem,
    showNotesEditor,
    openNotesEditor,
    // 批量
    handleSelectionChange,
    handleBatchDelete,
    handleBatchMoveToGroup,
    exportData,
    resetFilters,
    clearAllFilters
  };
}
