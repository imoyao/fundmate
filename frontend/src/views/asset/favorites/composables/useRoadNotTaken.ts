// 未竟之蹊（/the-road-not-taken）数据与交互编排。
//
// 数据来源（全部真实接口，无编造）：
// - GET /api/watchlist/favorites/                  主体清单
// - GET /api/watchlist/trends/?symbols=&days=      封面走势序列
// - GET /api/watchlist/tags/                       标签名/色
// - GET /api/watchlist/items/?status=cleared       已清仓 symbol 集合（状态推导）
// 写操作：PATCH /api/watchlist/items/{id}/、POST|DELETE .../tags/{tagId}/
//
// 设计预览（DEMO_ITEMS）仅在 previewMode 打开时追加，卡片带 isDemo 标记且禁止保存。

import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  addTagToItem,
  getFavorites,
  getWatchlistItems,
  getWatchlistTags,
  getWatchlistTrends,
  removeTagFromItem,
  updateWatchlistItem,
  type WatchlistItem,
  type WatchlistTag
} from "@/api/watchlist";
import type {
  RoadEntityType,
  RoadHoldingState,
  RoadItem,
  RoadStatusFilter
} from "@/types/favorites";
import {
  DEMO_ITEMS,
  PAGE_SIZE,
  SORT_OPTIONS,
  TREND_DAYS,
  toEntityType
} from "../constants";
import { daysFromToday } from "../helpers";

/** 后端行 → 卡片视图模型 */
function toRoadItem(raw: WatchlistItem, clearedSymbols: Set<string>): RoadItem {
  const hasPosition = (raw.holding_quantity ?? 0) > 0;
  const holdingState: RoadHoldingState = hasPosition
    ? "holding"
    : clearedSymbols.has(raw.symbol)
      ? "cleared"
      : "watching";
  return {
    id: raw.id,
    symbol: raw.symbol,
    market: raw.market,
    display_name: raw.display_name || raw.symbol,
    asset_type: raw.asset_type ?? null,
    venue: raw.venue ?? null,
    entity: toEntityType(raw.asset_type),
    holdingState,
    favorite_at: raw.favorite_at ?? null,
    next_review_date: raw.next_review_date ?? null,
    is_pinned: Boolean(raw.is_pinned),
    notes: raw.notes ?? null,
    notes_summary: raw.notes_summary ?? null,
    add_reason: raw.add_reason ?? null,
    tag_ids: raw.tag_ids ?? [],
    trend: [],
    current_price: raw.current_price ?? null,
    price_at_added: raw.price_at_added ?? null,
    holding_quantity: raw.holding_quantity ?? null,
    holding_pnl: raw.holding_pnl ?? null,
    holding_pnl_percent: raw.holding_pnl_percent ?? null,
    position_market_value: raw.position_market_value ?? null,
    created_at: raw.created_at ?? null,
    updated_at: raw.updated_at ?? null
  };
}

/** 是否进入「待复盘」：已设提醒且已到期或 7 天内到期 */
function isDueReview(item: RoadItem): boolean {
  const days = daysFromToday(item.next_review_date);
  return days != null && days <= 7;
}

export function useRoadNotTaken() {
  const items = ref<RoadItem[]>([]);
  const tags = ref<WatchlistTag[]>([]);
  const loading = ref(false);

  const entityFilter = ref<RoadEntityType | "all">("all");
  const statusFilter = ref<RoadStatusFilter>("all");
  const keyword = ref("");
  const sortBy = ref<string>(SORT_OPTIONS[0].value);
  const page = ref(1);

  /** 管理态（多选 + 批量操作） */
  const manageMode = ref(false);
  const selectedIds = ref<number[]>([]);
  /** 正在编辑的卡片 id */
  const editingId = ref<number | null>(null);
  /**
   * 设计预览：追加示例卡（基金经理等后端未落地能力时用于呈现设计）。
   * 仅限开发模式（pnpm dev）：生产构建中 import.meta.env.DEV 恒为 false，
   * 故预览默认关闭、UI 不渲染「示例」入口，生产分支永不出现示例卡且开关不可打开。
   */
  const previewMode = ref(import.meta.env.DEV);

  /**
   * 全量清单（含预览示例卡）。
   * 双重保险：即便 previewMode 被误置为 true，生产构建下 import.meta.env.DEV
   * 为 false，示例卡也不会追加（Rollup 亦会摇树 DEMO_ITEMS）。
   */
  const allItems = computed<RoadItem[]>(() =>
    previewMode.value && import.meta.env.DEV
      ? [...items.value, ...DEMO_ITEMS]
      : items.value
  );

  /** 按状态过滤后的基数（一级胶囊计数用） */
  const byStatus = computed<RoadItem[]>(() => {
    if (statusFilter.value === "all") return allItems.value;
    if (statusFilter.value === "review")
      return allItems.value.filter(isDueReview);
    return allItems.value.filter(i => i.holdingState === statusFilter.value);
  });

  /** 按类别过滤后的基数（二级胶囊计数用） */
  const byEntity = computed<RoadItem[]>(() =>
    entityFilter.value === "all"
      ? allItems.value
      : allItems.value.filter(i => i.entity === entityFilter.value)
  );

  const entityCounts = computed<Record<string, number>>(() => {
    const counts: Record<string, number> = { all: byStatus.value.length };
    for (const item of byStatus.value) {
      counts[item.entity] = (counts[item.entity] ?? 0) + 1;
    }
    return counts;
  });

  const statusCounts = computed<Record<string, number>>(() => {
    const counts: Record<string, number> = { all: byEntity.value.length };
    for (const item of byEntity.value) {
      counts[item.holdingState] = (counts[item.holdingState] ?? 0) + 1;
    }
    counts.review = byEntity.value.filter(isDueReview).length;
    return counts;
  });

  const filteredItems = computed<RoadItem[]>(() => {
    let list = byStatus.value.filter(i =>
      entityFilter.value === "all" ? true : i.entity === entityFilter.value
    );
    const kw = keyword.value.trim().toLowerCase();
    if (kw) {
      list = list.filter(
        i =>
          i.symbol.toLowerCase().includes(kw) ||
          i.display_name.toLowerCase().includes(kw)
      );
    }
    const sorted = [...list];
    if (sortBy.value === "favorite_at") {
      sorted.sort((a, b) =>
        (b.favorite_at ?? "").localeCompare(a.favorite_at ?? "")
      );
    } else if (sortBy.value === "next_review_date") {
      // 有复盘日期的按日期升序在前（越紧迫越靠前），未设置的沉到末尾
      sorted.sort((a, b) => {
        if (!a.next_review_date && !b.next_review_date) return 0;
        if (!a.next_review_date) return 1;
        if (!b.next_review_date) return -1;
        return a.next_review_date.localeCompare(b.next_review_date);
      });
    } else {
      sorted.sort((a, b) =>
        (b.updated_at ?? "").localeCompare(a.updated_at ?? "")
      );
    }
    // 置顶恒在顶部（与自选页心智一致）
    return sorted.sort((a, b) => Number(b.is_pinned) - Number(a.is_pinned));
  });

  const total = computed(() => filteredItems.value.length);
  const pageCount = computed(() =>
    Math.max(1, Math.ceil(total.value / PAGE_SIZE))
  );
  const pagedItems = computed<RoadItem[]>(() => {
    const start = (page.value - 1) * PAGE_SIZE;
    return filteredItems.value.slice(start, start + PAGE_SIZE);
  });
  const isLastPage = computed(() => page.value >= pageCount.value);

  function resetPage() {
    page.value = 1;
  }

  function setEntityFilter(key: RoadEntityType | "all") {
    entityFilter.value = key;
    resetPage();
  }

  function setStatusFilter(key: RoadStatusFilter) {
    statusFilter.value = key;
    resetPage();
  }

  // ─────────────── 数据加载 ───────────────
  async function loadTrends() {
    const symbols = [
      ...new Set(items.value.map(i => i.symbol).filter(Boolean))
    ].slice(0, 50);
    if (!symbols.length) return;
    try {
      const res = await getWatchlistTrends(symbols, TREND_DAYS);
      const map = res.data ?? {};
      for (const item of items.value) {
        item.trend = map[item.symbol] ?? [];
      }
    } catch {
      // 走势缺失不阻断页面：卡片封面降级为「走势积累中」
    }
  }

  async function load() {
    loading.value = true;
    try {
      const [favRes, tagRes, clearedRes] = await Promise.all([
        getFavorites(),
        getWatchlistTags(),
        getWatchlistItems({ status: "cleared", per_page: 200 })
      ]);
      const clearedSymbols = new Set(
        (clearedRes.data ?? []).map(i => i.symbol).filter(Boolean)
      );
      items.value = (favRes.data ?? []).map(i => toRoadItem(i, clearedSymbols));
      tags.value = tagRes.data ?? [];
      await loadTrends();
    } catch (e) {
      console.error("获取特别关注列表失败：", e);
      ElMessage.error("获取特别关注列表失败");
    } finally {
      loading.value = false;
    }
  }

  // ─────────────── 选择与管理态 ───────────────
  const selectedItems = computed(() =>
    allItems.value.filter(i => i.id != null && selectedIds.value.includes(i.id))
  );

  function toggleManage() {
    manageMode.value = !manageMode.value;
    if (!manageMode.value) selectedIds.value = [];
  }

  function toggleSelect(item: RoadItem) {
    if (item.id == null) return;
    selectedIds.value = selectedIds.value.includes(item.id)
      ? selectedIds.value.filter(id => id !== item.id)
      : [...selectedIds.value, item.id];
  }

  function clearSelection() {
    selectedIds.value = [];
  }

  /** 批量置顶 */
  async function batchPin() {
    const targets = selectedItems.value.filter(i => i.id != null);
    if (!targets.length) return;
    try {
      for (const item of targets) {
        await updateWatchlistItem(item.id as number, { is_pinned: true });
      }
      ElMessage.success(`已置顶 ${targets.length} 项`);
    } catch {
      ElMessage.error("批量置顶失败");
    } finally {
      clearSelection();
      manageMode.value = false;
      await load();
    }
  }

  /** 批量移出特别关注（回到普通自选） */
  async function batchRemove() {
    const targets = selectedItems.value.filter(i => i.id != null && !i.isDemo);
    if (!targets.length) return;
    try {
      for (const item of targets) {
        await updateWatchlistItem(item.id as number, { favorite: false });
      }
      ElMessage.success(`已移出 ${targets.length} 项`);
    } catch {
      ElMessage.error("批量移出失败");
    } finally {
      clearSelection();
      manageMode.value = false;
      await load();
    }
  }

  // ─────────────── 单卡操作 ───────────────
  /** 单卡置顶/取消置顶 */
  async function togglePin(item: RoadItem) {
    if (item.id == null || item.isDemo) return;
    try {
      await updateWatchlistItem(item.id, { is_pinned: !item.is_pinned });
      await load();
    } catch {
      ElMessage.error("置顶操作失败");
    }
  }

  /** 单卡移出特别关注（回到普通自选） */
  async function removeFavorite(item: RoadItem) {
    if (item.id == null || item.isDemo) return;
    try {
      await updateWatchlistItem(item.id, { favorite: false });
      ElMessage.success("已移回普通自选");
      await load();
    } catch {
      ElMessage.error("移出失败");
    }
  }

  // ─────────────── 单卡编辑 ───────────────
  function startEdit(item: RoadItem) {
    if (item.isDemo || item.id == null) return;
    editingId.value = item.id;
  }

  function cancelEdit() {
    editingId.value = null;
  }

  interface CardDraft {
    notes: string;
    next_review_date: string | null;
    tagIds: number[];
  }

  async function saveCard(item: RoadItem, draft: CardDraft) {
    if (item.isDemo || item.id == null) return;
    const itemId = item.id;
    try {
      await updateWatchlistItem(itemId, {
        notes: draft.notes,
        next_review_date: draft.next_review_date
      });
      const toAdd = draft.tagIds.filter(id => !item.tag_ids.includes(id));
      const toRemove = item.tag_ids.filter(id => !draft.tagIds.includes(id));
      await Promise.all([
        ...toAdd.map(id => addTagToItem(itemId, id)),
        ...toRemove.map(id => removeTagFromItem(itemId, id))
      ]);
      ElMessage.success("已保存");
      editingId.value = null;
      await load();
    } catch {
      ElMessage.error("保存失败");
    }
  }

  return {
    // state
    items: allItems,
    tags,
    loading,
    entityFilter,
    statusFilter,
    keyword,
    sortBy,
    page,
    manageMode,
    selectedIds,
    editingId,
    previewMode,
    // derived
    entityCounts,
    statusCounts,
    filteredItems,
    pagedItems,
    total,
    pageCount,
    isLastPage,
    selectedItems,
    // actions
    load,
    setEntityFilter,
    setStatusFilter,
    resetPage,
    toggleManage,
    toggleSelect,
    clearSelection,
    batchPin,
    batchRemove,
    togglePin,
    removeFavorite,
    startEdit,
    cancelEdit,
    saveCard
  };
}
