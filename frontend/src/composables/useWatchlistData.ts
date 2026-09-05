import { ref, computed, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  getWatchlistItems,
  updateWatchlistItem,
  deleteWatchlistItem,
  removeItemFromGroup,
  addItemToGroup,
  type WatchlistItem
} from "@/api/watchlist";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";

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
  batchMode: ReturnType<typeof ref<boolean>>;
  selectedItems: ReturnType<typeof ref<WatchlistItem[]>>;
  batchMoveGroupId: ReturnType<typeof ref<number | null>>;
}

export function useWatchlistData(
  groups: ReturnType<typeof useWatchlistGroups>,
  tags: ReturnType<typeof useWatchlistTags>,
  toolbar: WatchlistToolbarState
) {
  const { activeGroup, allGroups, activeCustomGroupId } = groups;
  const { selectedFilterTagIds } = tags;
  const {
    searchKeyword,
    currentView,
    batchMode,
    selectedItems,
    batchMoveGroupId
  } = toolbar;

  const loading = ref(false);
  const items = ref<WatchlistItem[]>([]);
  // 全量过滤结果（忽略分页）：供实时估值汇总条使用（#1245）。
  // 汇总（总市值/总成本/总盈亏）必须基于整组而非当前页，否则翻页时数据会跳变。
  const allItems = ref<WatchlistItem[]>([]);
  const currentPage = ref(1);
  const pageSize = ref(20);
  const totalItems = ref(0);

  // 用户列内排序状态（#991）：空串表示未排序（后端走默认置顶+更新时间）
  const sortBy = ref("");
  const sortOrder = ref<"asc" | "desc">("asc");

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
    // venue 过滤由顶部 el-segmented（currentView）唯一承担（方案 B 收敛三套入口）
    if (currentView.value === "exchange") params.venue = "EXCHANGE";
    else if (currentView.value === "otc") params.venue = "OTC";
    if (searchKeyword.value) params.q = searchKeyword.value;
    // 用户列内排序（#991）：仅白名单字段由后端校验，跨页排序一致
    if (sortBy.value) {
      params.sort_by = sortBy.value;
      params.sort_order = sortOrder.value;
    }
    return params;
  });

  /** 拉取列表（分页切片由后端完成，前端只消费 data/total）。
   * @param refreshAll 是否顺带刷新全量结果 allItems（供估值汇总条）。
   *        筛选/排序/搜索/分组变化时应传 true；纯翻页传 false（汇总保持稳定）。
   */
  async function fetchData(refreshAll = true) {
    loading.value = true;
    try {
      const res = await getWatchlistItems(fetchParams.value);
      items.value = res.data ?? [];
      totalItems.value = res.total ?? items.value.length;
      if (refreshAll) {
        await fetchAllItems();
      }
    } catch (e) {
      ElMessage.error("获取自选列表失败");
      console.error("获取自选列表错误：", e);
    } finally {
      loading.value = false;
    }
  }

  /**
   * 拉取「全量过滤结果」（忽略分页），供实时估值汇总条使用（#1245）。
   * 后端 per_page 上限 200，故按页累加直到取尽（安全阀防止异常死循环），
   * 确保汇总口径与整组一致、翻页时不再跳变。
   */
  async function fetchAllItems() {
    const base: Record<string, string | number | boolean> = {
      ...fetchParams.value
    };
    delete base.page;
    const all: WatchlistItem[] = [];
    const perPage = 200;
    for (let page = 1; page <= 50; page++) {
      const res = await getWatchlistItems({ ...base, page, per_page: perPage });
      const rows = (res.data ?? []) as WatchlistItem[];
      all.push(...rows);
      if (rows.length < perPage) break;
    }
    allItems.value = all;
  }

  // ─────────────────────────────────────────────
  // 排序 / 分页切换辅助
  // ─────────────────────────────────────────────

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

  /** 虚拟持仓行（id=null）无自选记录，置顶操作无意义，直接跳过 */
  async function handleTogglePin(row: WatchlistItem) {
    if (row.id == null) return;
    try {
      await updateWatchlistItem(row.id, { is_pinned: !row.is_pinned });
      ElMessage.success(row.is_pinned ? "已取消置顶" : "已置顶");
      fetchData();
    } catch (e) {
      ElMessage.error("置顶操作失败");
      console.error("置顶错误：", e);
    }
  }

  /** 虚拟持仓行（id=null）无自选记录，特别关注操作无意义，直接跳过 */
  async function handleToggleFavorite(row: WatchlistItem) {
    if (row.id == null) return;
    try {
      await updateWatchlistItem(row.id, { favorite: !row.favorite });
      ElMessage.success(row.favorite ? "已取消特别关注" : "已设为特别关注");
      fetchData();
    } catch (e) {
      ElMessage.error("关注操作失败");
      console.error("关注错误：", e);
    }
  }

  const removingItem = ref<WatchlistItem | null>(null);
  const removeScope = ref<"all" | "current">("all");
  const removeDialogVisible = ref(false);

  /** 点击移除：记录待移除项并弹确认框；虚拟持仓行直接跳过 */
  function confirmRemove(row: WatchlistItem) {
    if (row.id == null) return;
    removingItem.value = row;
    removeScope.value = "all";
    removeDialogVisible.value = true;
  }

  /** 执行移除：从当前分组移除（仅自定义分组）或彻底删除自选 */
  async function executeRemove() {
    const item = removingItem.value;
    if (!item || item.id == null) return;
    try {
      if (removeScope.value === "current" && activeCustomGroupId.value) {
        await removeItemFromGroup(item.id, activeCustomGroupId.value);
        ElMessage.success("已从当前分组移除");
      } else {
        await deleteWatchlistItem(item.id);
        ElMessage.success("已移除自选");
      }
      removeDialogVisible.value = false;
      fetchData();
    } catch (e) {
      ElMessage.error("移除操作失败");
      console.error("移除错误：", e);
    }
  }

  /** 行内标签编辑：无自选记录（id 为 null，如草稿态/聚合虚拟行）给出提示而非静默无反应；
     打开弹窗由页面负责（暴露 editingItem 与开关） */
  const editingItem = ref<WatchlistItem | null>(null);
  const showTagEditor = ref(false);
  function openTagEditor(row: WatchlistItem) {
    if (row.id == null) {
      ElMessage.warning("该资产尚未建立自选记录，暂不可添加标签");
      return;
    }
    editingItem.value = row;
    showTagEditor.value = true;
  }

  // ─────────────────────────────────────────────
  // 批量操作
  // ─────────────────────────────────────────────

  function handleSelectionChange(selection: WatchlistItem[]) {
    selectedItems.value = selection;
  }

  async function handleBatchDelete() {
    if (selectedItems.value.length === 0) return;
    try {
      await ElMessageBox.confirm(
        `确定要移除选中的 ${selectedItems.value.length} 个自选资产吗？`,
        "批量移除",
        { confirmButtonText: "确定", cancelButtonText: "取消", type: "warning" }
      );
      for (const item of selectedItems.value) {
        try {
          // 虚拟持仓行（id=null）无自选记录，不可删除，跳过
          if (item.id == null) continue;
          await deleteWatchlistItem(item.id);
        } catch {
          /* ignore */
        }
      }
      ElMessage.success("批量移除完成");
      batchMode.value = false;
      selectedItems.value = [];
      fetchData();
    } catch {
      /* 用户取消 */
    }
  }

  const handleBatchMoveToGroup = async (groupId: number | null) => {
    if (!groupId || selectedItems.value.length === 0) return;
    try {
      // 虚拟持仓行（id=null）无自选记录，不可移动，过滤后仅对真实自选行发起请求
      const promises = selectedItems.value
        .filter(
          (item): item is WatchlistItem & { id: number } => item.id != null
        )
        .map(item => addItemToGroup(item.id, groupId));
      await Promise.all(promises);
      ElMessage.success(
        `已将 ${selectedItems.value.length} 个资产移动到所选分组`
      );
      batchMoveGroupId.value = null;
      batchMode.value = false;
      selectedItems.value = [];
      fetchData();
    } catch {
      ElMessage.error("批量移动失败");
    }
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

  /** 重置全部筛选（搜索/分组/视图/标签），回弹到「持仓」默认态 */
  function resetFilters() {
    searchKeyword.value = "";
    groups.resetActiveGroup();
    currentView.value = "all";
    tags.resetTagFilter();
  }

  return {
    // 分页状态
    loading,
    items,
    allItems,
    currentPage,
    pageSize,
    totalItems,
    fetchParams,
    fetchData,
    handleSortChange,
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
    // 批量
    handleSelectionChange,
    handleBatchDelete,
    handleBatchMoveToGroup,
    exportData,
    resetFilters
  };
}
