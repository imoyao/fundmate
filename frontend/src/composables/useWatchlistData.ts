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
import { localForage } from "@/utils/localforage";
import {
  sortRowsForClient,
  type ClientSortKey,
  type ClientSortOrder
} from "@/views/asset/watchlist/clientSort";
import {
  DEFAULT_SORT_METRIC,
  normalizeSortMetric,
  type SortMetric
} from "@/views/asset/watchlist/sortMetric";

/** 每页条数可选档位（issue #1335）：与后端 per_page 限幅 [1,200] 对齐，不超出范围 */
export const PAGE_SIZE_OPTIONS = [20, 50, 100] as const;
const PAGE_SIZE_STORAGE_KEY = "watchlist-page-size";
const DEFAULT_PAGE_SIZE = 20;

/**
 * 每页条数偏好（issue #1335）：纯前端本地持久化（localforage），不落数据库——
 * 跨设备同步依赖后端 user_preferences 基建，本期不做（见 issue 关联说明）。
 * 模块级单例：自选页与设置抽屉共享同一份状态，且只从本地加载一次。
 */
const pageSize = ref(DEFAULT_PAGE_SIZE);
// 记忆化「加载本地每页条数」Promise：多个挂载点（自选页 + 设置抽屉）并发调用 initPageSize 时，
// 共享同一次加载，避免第二个挂载点在首个 await 完成前即返回、用默认 20 发起首屏请求，
// 随后被记忆值（如 50）覆盖导致「数据按 20 拉取、分页器按 50 显示」的短暂不一致。
let pageSizeLoadPromise: Promise<void> | null = null;

async function loadPageSize(): Promise<void> {
  try {
    const saved = await localForage().getItem<number>(PAGE_SIZE_STORAGE_KEY);
    if (
      typeof saved === "number" &&
      (PAGE_SIZE_OPTIONS as readonly number[]).includes(saved)
    ) {
      pageSize.value = saved;
    }
  } catch {
    /* 读取失败按默认处理 */
  }
}

function persistPageSize(): void {
  localForage()
    .setItem<number>(PAGE_SIZE_STORAGE_KEY, pageSize.value)
    .catch(() => {
      /* 持久化失败不影响会话内生效（IndexedDB 不可用时库内部降级 localStorage） */
    });
}

/**
 * 复合列的排序口径（按列 key 记忆，2026-10-30 二次优化）。
 *
 * 三个复合列各有各的两行数（当日盈亏：金额/涨幅；持仓市值：金额/占比；
 * 持仓收益：金额/收益率），故记忆的是 `{ [列 key]: SortMetric }` 而不是单个值——
 * 首版只服务当日盈亏，用的是单值 ref，扩到三列后必须按列存，否则切一列会把
 * 另一列的口径一起改掉。
 *
 * 纯本地记忆（与 pageSize 同模式，不上云）：它是「我怎么看这张表」的偏好，
 * 跨设备同步的价值低于实现成本；服务端的 user_preferences 里也还没有这一项。
 * 模块级单例：表头徽标与数据层共享同一份，切换即时生效。
 */
const SORT_METRICS_STORAGE_KEY = "watchlist-sort-metrics";
/** 首版的单值键（只存当日盈亏，取值 amount/pct）：读一次做迁移，之后不再写 */
const LEGACY_DAY_PNL_METRIC_STORAGE_KEY = "watchlist-day-pnl-metric";
const sortMetrics = ref<Record<string, SortMetric>>({});
let sortMetricsLoadStarted = false;

async function loadSortMetrics(): Promise<void> {
  if (sortMetricsLoadStarted) return;
  sortMetricsLoadStarted = true;
  try {
    const saved = await localForage().getItem<Record<string, unknown>>(
      SORT_METRICS_STORAGE_KEY
    );
    const next: Record<string, SortMetric> = {};
    if (saved && typeof saved === "object") {
      for (const [key, raw] of Object.entries(saved)) {
        const metric = normalizeSortMetric(raw);
        if (metric) next[key] = metric;
      }
    }
    // 迁移：老用户存过「按涨幅排序」，不读旧键会静默回落成「按金额」
    if (!next.day_pnl) {
      const legacy = await localForage().getItem<unknown>(
        LEGACY_DAY_PNL_METRIC_STORAGE_KEY
      );
      const migrated = normalizeSortMetric(legacy);
      if (migrated) next.day_pnl = migrated;
    }
    sortMetrics.value = next;
  } catch {
    /* 读取失败按默认（金额，与列主行一致） */
  }
}

/** 取某列的当前口径；未存过 → 金额（与列主行一致） */
function sortMetricOf(key: string): SortMetric {
  return sortMetrics.value[key] ?? DEFAULT_SORT_METRIC;
}

function setSortMetric(key: string, metric: SortMetric): void {
  if (sortMetricOf(key) === metric) return;
  // 换新对象而不是改属性：引用变化让读它的 computed（整组排序）稳定重算
  sortMetrics.value = { ...sortMetrics.value, [key]: metric };
  localForage()
    .setItem(SORT_METRICS_STORAGE_KEY, sortMetrics.value)
    .catch(() => {
      /* 持久化失败不影响本次会话 */
    });
}

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

  // 口径偏好首屏前恢复（幂等；失败静默回默认「金额」）
  void loadSortMetrics();

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
   * 幂等：返回记忆化的加载 Promise，所有调用方（自选页、设置抽屉等挂载点）等待同一次加载完成，
   * 避免并发挂载点时第二个调用方提前返回、用默认档位发起首屏请求而产生短暂不一致。
   */
  async function initPageSize(): Promise<void> {
    if (!pageSizeLoadPromise) {
      pageSizeLoadPromise = loadPageSize();
    }
    return pageSizeLoadPromise;
  }

  /** 切换每页条数（#1335）：记忆选择 → 回到第一页 → 重新拉取。
   *  仅接受预定义档位，越界值回退默认，避免与后端 per_page 限幅 [1,200] 冲突。 */
  function setPageSize(size: number) {
    const allowed = PAGE_SIZE_OPTIONS as readonly number[];
    const next = allowed.includes(size) ? size : DEFAULT_PAGE_SIZE;
    if (next === pageSize.value) return;
    pageSize.value = next;
    persistPageSize();
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
    // 默认范围按**用户所在视图**分流（用户心智模型：在哪个视图里点的移除，就先做那个视图
    // 对应的移除）——自定义分组内默认「仅从当前分组移除」；系统分组/全部视图没有
    // 「当前分组」可言，默认彻底删除。破坏性的「从所有分组移除并删除」必须由用户显式改选
    // （弹窗内另有警示文案，双保险，见 WatchlistRemoveDialog）。
    removeScope.value = currentIsCustom.value ? "current" : "all";
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
        // 防御性闸门：持仓资产禁止彻底删除（持仓即自选 #1458，删除无意义）。
        // 正常路径已被两层 UI 挡住——系统分组视图操作列按钮禁用、自定义分组视图
        // 弹窗「从所有分组移除并删除」单选禁用；这里兜底防止状态残留或未来复用
        // 本函数的新入口绕过两层 UI 直接删。
        if (item.status === "HOLDING") {
          ElMessage.warning("持仓资产无法从自选彻底删除，请先处理持仓");
          return;
        }
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
  // 批量操作
  // ─────────────────────────────────────────────

  function handleSelectionChange(selection: WatchlistItem[]) {
    selectedItems.value = selection;
  }

  async function handleBatchDelete() {
    if (selectedItems.value.length === 0) return;
    // 持仓资产不可彻底删除（持仓即自选 #1458，删除无意义）：与单行移除按钮、
    // executeRemove 的闸门保持一致——批量删除同样跳过持仓行并明示数量，
    // 否则「单行拦得住、批量拦不住」，语义分裂（虚拟持仓行 id=null 本就不可删，一并过滤）。
    const deletable = selectedItems.value.filter(
      (item): item is WatchlistItem & { id: number } =>
        item.id != null && item.status !== "HOLDING"
    );
    const holdingCount = selectedItems.value.length - deletable.length;
    if (deletable.length === 0) {
      ElMessage.warning(
        selectedItems.value.some(item => item.status === "HOLDING")
          ? "选中的均为持仓资产，无法从自选彻底删除，请先处理持仓"
          : "选中的自选资产缺少主键，无法删除，请刷新后重试"
      );
      return;
    }
    try {
      await ElMessageBox.confirm(
        holdingCount > 0
          ? `确定要移除选中的 ${deletable.length} 个自选资产吗？` +
              `（持仓资产 ${holdingCount} 个不可删除，将跳过）`
          : `确定要移除选中的 ${deletable.length} 个自选资产吗？`,
        "批量移除",
        { confirmButtonText: "确定", cancelButtonText: "取消", type: "warning" }
      );
      for (const item of deletable) {
        try {
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

  const handleBatchMoveToGroup = async (groupId: number | null | undefined) => {
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
      batchMoveGroupId.value = undefined;
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
