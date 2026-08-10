# batch3 浠ｇ爜鎵嬪唽锛堝彲鐩存帴闃呰鐨勫叏閮ㄦ簮鐮侊級

> 鏈枃浠剁敱 `fundmate-optimization/batch3/` 涓嬪疄闄呬氦浠樻枃浠跺師鏍锋嫾鍚堬紝鐢ㄤ簬鍦ㄤ粎鏀寔 Markdown 鐨勫鎴风閲岄槄璇绘簮鐮併€?
> 鍏?16 涓枃浠躲€?

## `composables/watchlist/constants.ts`

```ts
// ============================================================================
// 鑷€夎偂妯″潡甯搁噺
// ----------------------------------------------------------------------------
// 鎶界鑷?watchlist/index.vue 涓殑 systemGroups / VENUE_FILTER_OPTIONS /
// presetColors 绛夌‖缂栫爜甯搁噺锛岀粺涓€涓哄崟涓€鏉ユ簮锛坰ingle source of truth锛夈€?// ============================================================================
import type { SystemGroupType, VenueFilter, WatchlistGroup } from "./types";

/** 绯荤粺鍒嗙粍瀹氫箟锛堜笉鍙噸鍛藉悕 / 涓嶅彲鍒犻櫎锛?*/
export const SYSTEM_GROUPS: WatchlistGroup[] = [
  { id: "all", name: "鍏ㄩ儴", is_system: true, type: "all" },
  { id: "exchange", name: "鍦哄唴", is_system: true, type: "exchange" },
  { id: "otc", name: "鍦哄", is_system: true, type: "otc" },
  { id: "favorite", name: "鏀惰棌", is_system: true, type: "favorite" },
  { id: "pinned", name: "缃《", is_system: true, type: "pinned" }
];

/** 椤堕儴銆屽叏閮?/ 鍦哄唴 / 鍦哄銆嶅垎娈佃鍥鹃€夐」锛堜笌 systemGroups 鐨勫墠涓夐」瀵归綈锛?*/
export const VIEW_OPTIONS: { label: string; value: SystemGroupType }[] = [
  { label: "鍏ㄩ儴", value: "all" },
  { label: "鍦哄唴", value: "exchange" },
  { label: "鍦哄", value: "otc" }
];

/** 鍦洪杩囨护鎸夐挳閫夐」 */
export const VENUE_FILTER_OPTIONS: { label: string; value: VenueFilter }[] = [
  { label: "鍏ㄩ儴", value: "all" },
  { label: "鍦哄唴", value: "EXCHANGE" },
  { label: "鍦哄", value: "OTC" }
];

/** 鏍囩棰滆壊棰勮鑹叉澘 */
export const PRESET_TAG_COLORS: string[] = [
  "#f56c6c",
  "#e6a23c",
  "#67c23a",
  "#409eff",
  "#909399",
  "#9254de",
  "#13c2c2",
  "#eb2f96"
];

/** 榛樿姣忛〉鏉℃暟 */
export const DEFAULT_PAGE_SIZE = 20;
```

## `composables/watchlist/context.ts`

```ts
// ============================================================================
// watchlist 涓婁笅鏂囷細provide / inject 娉ㄥ叆閿?+ 绫诲瀷
// ----------------------------------------------------------------------------
// 澹崇粍浠?WatchlistIndex.vue 缁勮鍏ㄩ儴 composable 杩斿洖鍊硷紝缁熶竴 provide锛?// 鍚勫瓙缁勪欢閫氳繃 useWatchlistContext() 娉ㄥ叆锛岄伩鍏?prop 閫忎紶涓庨噸澶嶅疄渚嬪寲銆?// 杩欎笌 batch2 鐨?import 鍚戝閲囩敤鍚屼竴濂楁満鍒讹紝淇濇寔鏋舵瀯涓€鑷淬€?// ============================================================================
import { inject } from "vue";
import type { InjectionKey } from "vue";
import type { useWatchlistCore } from "./useWatchlistCore";
import type { useWatchlistGroups } from "./useWatchlistGroups";
import type { useTableFilters } from "./useTableFilters";
import type { useBatchActions } from "./useBatchActions";
import type { useTagManager } from "./useTagManager";
import type { useRowTagEditor } from "./useRowTagEditor";

/** 鍏ㄩ噺涓婁笅鏂囷細鎵€鏈?composable 杩斿洖鍊肩殑闆嗗悎 */
export interface WatchlistContext {
  core: ReturnType<typeof useWatchlistCore>;
  groups: ReturnType<typeof useWatchlistGroups>;
  filters: ReturnType<typeof useTableFilters>;
  batch: ReturnType<typeof useBatchActions>;
  tagManager: ReturnType<typeof useTagManager>;
  rowTagEditor: ReturnType<typeof useRowTagEditor>;
}

export const watchlistContextKey: InjectionKey<WatchlistContext> = Symbol(
  "watchlistContext"
);

/** 瀛愮粍浠舵敞鍏ヤ笂涓嬫枃锛堝繀椤诲湪 provide 涔嬩笅璋冪敤锛?*/
export function useWatchlistContext(): WatchlistContext {
  const ctx = inject(watchlistContextKey);
  if (!ctx) {
    throw new Error(
      "useWatchlistContext() 蹇呴』鍦?WatchlistIndex.vue 鎻愪緵鐨?watchlistContextKey 涔嬩笅浣跨敤"
    );
  }
  return ctx;
}
```

## `composables/watchlist/index.ts`

```ts
// ============================================================================
// watchlist composables 缁熶竴鍑哄彛锛坆arrel锛?// ----------------------------------------------------------------------------
// 浣跨敤鏂圭粺涓€浠庤繖閲屽鍏ワ細import { useWatchlistCore, useWatchlistContext } from "@/composables/watchlist"
// ============================================================================
export * from "./types";
export * from "./constants";
export * from "./useWatchlistCore";
export * from "./useWatchlistGroups";
export * from "./useTableFilters";
export * from "./useBatchActions";
export * from "./useTagManager";
export * from "./useRowTagEditor";
export * from "./context";
```

## `composables/watchlist/types.ts`

```ts
// ============================================================================
// 鑷€夎偂锛坵atchlist锛夋ā鍧楃被鍨嬪畾涔?// ----------------------------------------------------------------------------
// 鏈枃浠堕泦涓０鏄庤嚜閫夎偂椤甸潰鍚?composable / 缁勪欢涔嬮棿鍏变韩鐨勬暟鎹粨鏋勩€?// 鎶界鑷?frontend/src/views/asset/watchlist/index.vue锛堝師 62.6KB 鍗曟枃浠剁粍浠讹級銆?// 鍛藉悕涓庢簮鏂囦欢淇濇寔涓€鑷达細item / group / tag 涓?@/api/watchlist 杩斿洖缁撴瀯瀵归綈銆?// ============================================================================

/** 椤堕儴鍒嗘瑙嗗浘妯″紡锛氬叏閮?/ 鍦哄唴 / 鍦哄 */
export type ViewMode = "all" | "exchange" | "otc";

/** 鍦洪杩囨护锛氬叏閮?/ 浜ゆ槗鎵€ / 鍦哄 */
export type VenueFilter = "all" | "EXCHANGE" | "OTC";

/** 绉婚櫎鑼冨洿锛氫粠鍏ㄩ儴鍒嗙粍绉婚櫎 / 浠呬粠褰撳墠鍒嗙粍绉婚櫎 */
export type RemoveScope = "all" | "current";

/** 绯荤粺鍒嗙粍绫诲瀷鏍囪瘑 */
export type SystemGroupType =
  | "all"
  | "exchange"
  | "otc"
  | "favorite"
  | "pinned";

/** 鑷€夎偂鏉＄洰 */
export interface WatchlistItem {
  id: number;
  /** 鏍囩殑浠ｇ爜锛堝鍩洪噾浠ｇ爜銆佽偂绁ㄤ唬鐮侊級 */
  code: string;
  /** 鏍囩殑鍚嶇О */
  name: string;
  /** 瀹炴椂琛屾儏鐢ㄧ殑鍞竴鏍囪瘑锛坰ymbol锛?*/
  symbol: string;
  /** 璧勪骇绫诲瀷锛岀敤浜?AssetTypeBadge 绛夊睍绀?*/
  asset_type: string;
  /** 鍦洪锛欵XCHANGE / OTC */
  venue?: VenueFilter | string;
  /** 鏄惁缃《 */
  is_pinned: boolean;
  /** 鏄惁鏀惰棌 */
  is_favorite: boolean;
  /** 甯傚€硷紙瀹炴椂浼板€肩敤锛屽彲缂虹渷锛?*/
  market_value?: number;
  /** 鏈€鏂颁环锛堝疄鏃朵及鍊肩敤锛屽彲缂虹渷锛?*/
  price?: number;
  /** 娑ㄨ穼骞咃紙灞曠ず鐢紝鍙己鐪侊級 */
  change_percent?: number;
  /** 鍏宠仈鏍囩 id 鍒楄〃 */
  tags?: number[];
  /** 鎵€灞炶嚜瀹氫箟鍒嗙粍 id 鍒楄〃 */
  group_ids?: number[];
  /** 鍏佽鍚庣杩斿洖鐨勫叾浠栨墿灞曞瓧娈?*/
  [key: string]: any;
}

/** 鍒嗙粍锛堢郴缁熷垎缁?+ 鑷畾涔夊垎缁勭粺涓€缁撴瀯锛?*/
export interface WatchlistGroup {
  /** 绯荤粺鍒嗙粍鐢ㄥ瓧绗︿覆 key锛坅ll/exchange/otc/favorite/pinned锛夛紝鑷畾涔夊垎缁勭敤鏁板瓧 id */
  id: number | string;
  name: string;
  /** 鏄惁涓虹郴缁熷垎缁勶紙绯荤粺鍒嗙粍涓嶅彲閲嶅懡鍚?鍒犻櫎锛?*/
  is_system?: boolean;
  /** 绯荤粺鍒嗙粍绫诲瀷鏍囪瘑 */
  type?: SystemGroupType;
}

/** 鏍囩 */
export interface WatchlistTag {
  id: number;
  name: string;
  /** 棰滆壊鑹插€硷紙hex锛?*/
  color: string;
}

/** 鎷夊彇鑷€夎偂鍒楄〃鐨勮姹傚弬鏁帮紙涓?fetchParams 璁＄畻灞炴€у榻愶級 */
export interface WatchlistFetchParams {
  /** 褰撳墠鍒嗙粍锛堢郴缁熷垎缁?key 鎴栬嚜瀹氫箟鍒嗙粍 id锛?*/
  group?: string | number;
  /** 鎼滅储鍏抽敭瀛?*/
  keyword?: string;
  /** 鍦洪杩囨护 */
  venue?: VenueFilter;
  /** 鏍囩杩囨护 id 鍒楄〃 */
  tag_ids?: number[];
  /** 鍒嗛〉椤电爜 */
  page?: number;
  /** 姣忛〉鏉℃暟 */
  page_size?: number;
  [key: string]: any;
}

/** 瀹炴椂浼板€奸」锛堟潵鑷?useRealtimeQuotes锛?*/
export interface RealtimeQuoteItem {
  symbol: string;
  price?: number;
  changePercent?: number;
  marketValue?: number;
  [key: string]: any;
}

/** 瀹炴椂浼板€兼眹鎬?*/
export interface RealtimeSummary {
  totalMarketValue?: number;
  totalProfit?: number;
  totalProfitPercent?: number;
  [key: string]: any;
}
```

## `composables/watchlist/useBatchActions.ts`

```ts
// ============================================================================
// useBatchActions 鈥斺€?鎵归噺鎿嶄綔锛堝閫?/ 鎵归噺鍒犻櫎 / 鎵归噺绉荤粍锛塩omposable
// ----------------------------------------------------------------------------
// 鎶界鑷?watchlist/index.vue 鐨勬壒閲忔ā寮忓伐鍏锋爮閫昏緫銆?// 渚濊禆 core锛堝叡浜?selectedItems 鐨勫垹闄ら渶鍒锋柊鍒楄〃锛夈€?// ============================================================================
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { deleteWatchlistItem, addItemToGroup } from "@/api/watchlist";
import type { WatchlistItem } from "./types";

type Core = ReturnType<typeof import("./useWatchlistCore").useWatchlistCore>;

export function useBatchActions(core: Core) {
  const batchMode = ref(false);
  const selectedItems = ref<WatchlistItem[]>([]);
  const batchMoveGroupId = ref<number | string | null>(null);

  function toggleBatchMode() {
    batchMode.value = !batchMode.value;
    selectedItems.value = [];
    batchMoveGroupId.value = null;
  }

  function handleSelectionChange(selection: WatchlistItem[]) {
    selectedItems.value = selection;
  }

  async function handleBatchDelete() {
    if (!selectedItems.value.length) {
      ElMessage.warning("璇峰厛閫夋嫨瑕佸垹闄ょ殑鏉＄洰");
      return;
    }
    try {
      await ElMessageBox.confirm(
        `纭畾鍒犻櫎閫変腑鐨?${selectedItems.value.length} 涓潯鐩紵`,
        "鎵归噺鍒犻櫎",
        { type: "warning" }
      );
    } catch {
      return;
    }
    for (const item of selectedItems.value) {
      await deleteWatchlistItem(item.id);
    }
    selectedItems.value = [];
    batchMode.value = false;
    core.currentPage.value = 1;
    core.fetchData();
    ElMessage.success("宸叉壒閲忓垹闄?);
  }

  async function handleBatchMoveToGroup(groupId: number) {
    if (!selectedItems.value.length) {
      ElMessage.warning("璇峰厛閫夋嫨鏉＄洰");
      return;
    }
    for (const item of selectedItems.value) {
      await addItemToGroup(item.id, groupId);
    }
    ElMessage.success("宸茬Щ鍔ㄥ埌鍒嗙粍");
    selectedItems.value = [];
  }

  return {
    batchMode,
    selectedItems,
    batchMoveGroupId,
    toggleBatchMode,
    handleSelectionChange,
    handleBatchDelete,
    handleBatchMoveToGroup
  };
}
```

## `composables/watchlist/useRowTagEditor.ts`

```ts
// ============================================================================
// useRowTagEditor 鈥斺€?鍗曡鏍囩缂栬緫寮圭獥 composable
// ----------------------------------------------------------------------------
// 鎶界鑷?watchlist/index.vue 鐨勩€岀紪杈戞爣绛俱€嶅璇濇閫昏緫锛?//   涓哄崟涓嚜閫夋潯鐩鍒犳爣绛撅紙鍚鍐呮柊寤烘爣绛撅級銆?// 鏍囩鏁版嵁婧愭潵鑷?core.allTags锛涗繚瀛樻椂鎸夊樊寮傝皟鐢?add/remove 鎺ュ彛銆?// ============================================================================
import { ref, computed } from "vue";
import { ElMessage } from "element-plus";
import {
  addTagToItem,
  removeTagFromItem,
  createWatchlistTag
} from "@/api/watchlist";
import { PRESET_TAG_COLORS } from "./constants";
import type { WatchlistItem } from "./types";

type Core = ReturnType<typeof import("./useWatchlistCore").useWatchlistCore>;

export function useRowTagEditor(core: Core) {
  const showTagEditor = ref(false);
  const editingItem = ref<WatchlistItem | null>(null);
  /** 褰撳墠鏉＄洰鐨勬爣绛惧伐浣滃壇鏈紙閬垮厤鐩存帴鏀瑰姩鍘熷鏁版嵁锛?*/
  const editingItemNewTagIds = ref<number[]>([]);
  const savingTags = ref(false);
  const showNewTagFormInEditor = ref(false);
  const newTagNameInEditor = ref("");
  const newTagColorInEditor = ref(PRESET_TAG_COLORS[0]);

  /** 璇ユ潯鐩凡浣跨敤鐨勬爣绛?id */
  const usedTagIds = computed<number[]>(() => editingItem.value?.tags ?? []);
  /** 鍙緵閫夋嫨鐨勬爣绛撅紙鎺掗櫎宸蹭娇鐢ㄧ殑锛?*/
  const availableTagsForEditor = computed(() =>
    core.allTags.value.filter((t) => !usedTagIds.value.includes(t.id))
  );

  function openTagEditor(row: WatchlistItem) {
    editingItem.value = row;
    editingItemNewTagIds.value = [...(row.tags ?? [])];
    showNewTagFormInEditor.value = false;
    newTagNameInEditor.value = "";
    newTagColorInEditor.value = PRESET_TAG_COLORS[0];
    showTagEditor.value = true;
  }

  /** 閫夋嫨娓呯┖鏃堕€€鍑虹紪杈戞€侊紙涓庡師閫昏緫涓€鑷达級 */
  function handleSelectChange() {
    if (!editingItemNewTagIds.value.length) {
      // 鍏佽涓虹┖锛屼粎鎻愮ず
    }
  }

  function removeTagFromEditingItem(id: number) {
    editingItemNewTagIds.value = editingItemNewTagIds.value.filter((t) => t !== id);
  }

  async function createTagInEditor() {
    const name = newTagNameInEditor.value.trim();
    if (!name) {
      ElMessage.warning("璇疯緭鍏ユ爣绛惧悕");
      return;
    }
    const tag = await createWatchlistTag({ name, color: newTagColorInEditor.value });
    const newId: number = typeof tag === "number" ? tag : (tag as any).id;
    editingItemNewTagIds.value.push(newId);
    newTagNameInEditor.value = "";
    newTagColorInEditor.value = PRESET_TAG_COLORS[0];
    showNewTagFormInEditor.value = false;
    await core.fetchTags();
  }

  async function saveTagChanges() {
    const row = editingItem.value;
    if (!row) return;
    savingTags.value = true;
    try {
      const before = new Set(usedTagIds.value);
      const after = new Set(editingItemNewTagIds.value);
      // 鏂板
      for (const id of after) {
        if (!before.has(id)) await addTagToItem(row.id, id);
      }
      // 绉婚櫎
      for (const id of before) {
        if (!after.has(id)) await removeTagFromItem(row.id, id);
      }
      // 鍚屾鍥炲師鏁版嵁锛岄伩鍏嶅啀娆℃墦寮€鏃堕敊浣?      row.tags = [...editingItemNewTagIds.value];
      showTagEditor.value = false;
      editingItem.value = null;
      ElMessage.success("鏍囩宸蹭繚瀛?);
    } finally {
      savingTags.value = false;
    }
  }

  return {
    // 鐘舵€?    showTagEditor,
    editingItem,
    editingItemNewTagIds,
    savingTags,
    showNewTagFormInEditor,
    newTagNameInEditor,
    newTagColorInEditor,
    presetColors: PRESET_TAG_COLORS,
    // 娲剧敓
    usedTagIds,
    availableTagsForEditor,
    // 鍔ㄤ綔
    openTagEditor,
    handleSelectChange,
    removeTagFromEditingItem,
    createTagInEditor,
    saveTagChanges
  };
}
```

## `composables/watchlist/useTableFilters.ts`

```ts
// ============================================================================
// useTableFilters 鈥斺€?琛ㄦ牸杩囨护锛堣鍥?/ 鎼滅储 / 鍦洪 / 鏍囩锛塩omposable
// ----------------------------------------------------------------------------
// 鎶界鑷?watchlist/index.vue 鐨勩€岃繃婊ゃ€嶇浉鍏崇姸鎬併€?// 鍏抽敭绾﹀畾锛氭湰 composable 鍙礋璐ｃ€屼慨鏀硅繃婊ょ姸鎬併€嶏紝涓嶄富鍔ㄨ皟鐢?fetchData锛?//           鍒楄〃鍒锋柊缁熶竴鐢卞３缁勪欢锛圵atchlistIndex.vue锛夌殑鍗曚竴 watcher 椹卞姩锛?//           浠ラ伩鍏嶅垎缁勫垏鎹?+ 杩囨护鍙樺寲瀵艰嚧鐨勯噸澶嶈姹傘€?// ============================================================================
import { ref, computed } from "vue";
import type { ViewMode, VenueFilter } from "./types";
import { VENUE_FILTER_OPTIONS } from "./constants";

type Core = ReturnType<typeof import("./useWatchlistCore").useWatchlistCore>;

export function useTableFilters(core: Core) {
  const currentView = ref<ViewMode>("all");
  const searchKeyword = ref("");
  const currentVenueFilter = ref<VenueFilter>("all");
  const selectedFilterTagIds = ref<number[]>([]);

  /** 鍚勫満棣嗘暟閲忕粺璁★紙鍩轰簬褰撳墠鍒楄〃锛岀敤浜庤繃婊ゆ爮瑙掓爣锛?*/
  const venueStats = computed(() => {
    const stats = { all: core.items.value.length, EXCHANGE: 0, OTC: 0 } as Record<string, number>;
    for (const it of core.items.value) {
      if (it.venue === "EXCHANGE") stats.EXCHANGE += 1;
      else if (it.venue === "OTC") stats.OTC += 1;
    }
    return stats;
  });

  /** 鎷夊彇鍙傛暟锛堜笉鍚?group鈥斺€攇roup 鐢卞３缁勪欢鍚堝苟 activeGroup 娉ㄥ叆锛?*/
  const fetchParams = computed(() => {
    const p: Record<string, any> = {};
    if (searchKeyword.value) p.keyword = searchKeyword.value;
    if (currentVenueFilter.value !== "all") p.venue = currentVenueFilter.value;
    if (selectedFilterTagIds.value.length) p.tag_ids = selectedFilterTagIds.value;
    return p;
  });

  function setVenueFilter(venue: VenueFilter) {
    currentVenueFilter.value = venue;
  }

  /** 鍒嗘瑙嗗浘鍒囨崲锛氬悓姝ラ┍鍔ㄥ垎缁勶紙all/exchange/otc 瀵瑰簲绯荤粺鍒嗙粍锛?*/
  function handleViewChange(val: ViewMode) {
    currentView.value = val;
    core.activeGroup.value = val;
  }

  // 鎼滅储闃叉姈锛?00ms锛?  let searchTimer: ReturnType<typeof setTimeout> | null = null;
  function debounceSearch() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      // searchKeyword 宸插弻鍚戠粦瀹氾紝杩欓噷浠呯敤浜庤Е鍙?fetchParams 鍙樺寲
    }, 300);
  }

  function handleTagFilterChange() {
    // selectedFilterTagIds 鍙樺寲鍗宠Е鍙?fetchParams 鍙樺寲锛岀敱澹崇粍浠?watcher 鍒锋柊
  }

  function resetFilters() {
    currentView.value = "all";
    searchKeyword.value = "";
    currentVenueFilter.value = "all";
    selectedFilterTagIds.value = [];
    core.activeGroup.value = "all";
  }

  return {
    // 鐘舵€?    currentView,
    searchKeyword,
    currentVenueFilter,
    selectedFilterTagIds,
    venueStats,
    fetchParams,
    // 娲剧敓
    venueFilterOptions: VENUE_FILTER_OPTIONS,
    // 鍔ㄤ綔
    setVenueFilter,
    handleViewChange,
    debounceSearch,
    handleTagFilterChange,
    resetFilters
  };
}
```

## `composables/watchlist/useTagManager.ts`

```ts
// ============================================================================
// useTagManager 鈥斺€?鍏ㄥ眬鏍囩绠＄悊寮圭獥 composable
// ----------------------------------------------------------------------------
// 鎶界鑷?watchlist/index.vue 鐨勩€岀鐞嗘爣绛俱€嶅璇濇閫昏緫锛?//   鏂板缓 / 閲嶅懡鍚?/ 鏀硅壊 / 鍒犻櫎鏍囩锛堝叏灞€缁村害锛夈€?// 鏍囩鏁版嵁婧愭潵鑷?core.allTags銆?// ============================================================================
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createWatchlistTag,
  updateWatchlistTag,
  deleteWatchlistTag
} from "@/api/watchlist";
import { PRESET_TAG_COLORS } from "./constants";
import type { WatchlistTag } from "./types";

type Core = ReturnType<typeof import("./useWatchlistCore").useWatchlistCore>;

export function useTagManager(core: Core) {
  const showTagManager = ref(false);
  const editingTagId = ref<number | null>(null);
  const editTagName = ref("");
  const editTagColor = ref("");
  const selectedTagIdsForManager = ref<number[]>([]);
  const newTagNameInManager = ref("");
  const newTagColorInManager = ref(PRESET_TAG_COLORS[0]);
  const editInputRef = ref<HTMLElement | null>(null);

  function openTagManager() {
    showTagManager.value = true;
  }

  /** 閫変腑鏌愭爣绛捐繘鍏ョ紪杈戞€?*/
  function selectTagForEdit(id: number) {
    const tag = core.allTags.value.find((t) => t.id === id) as WatchlistTag | undefined;
    if (!tag) return;
    editingTagId.value = id;
    editTagName.value = tag.name;
    editTagColor.value = tag.color;
  }

  function removeTagFromSelection(id: number) {
    selectedTagIdsForManager.value = selectedTagIdsForManager.value.filter(
      (t) => t !== id
    );
  }

  async function addNewTagInManager() {
    const name = newTagNameInManager.value.trim();
    if (!name) {
      ElMessage.warning("璇疯緭鍏ユ爣绛惧悕");
      return;
    }
    await createWatchlistTag({ name, color: newTagColorInManager.value });
    newTagNameInManager.value = "";
    newTagColorInManager.value = PRESET_TAG_COLORS[0];
    await core.fetchTags();
    ElMessage.success("鏍囩宸插垱寤?);
  }

  async function saveEditTag(id: number) {
    const name = editTagName.value.trim();
    if (!name) {
      ElMessage.warning("鏍囩鍚嶄笉鑳戒负绌?);
      return;
    }
    await updateWatchlistTag(id, { name, color: editTagColor.value });
    editingTagId.value = null;
    editTagName.value = "";
    editTagColor.value = "";
    await core.fetchTags();
    ElMessage.success("鏍囩宸叉洿鏂?);
  }

  async function deleteTag(id: number) {
    try {
      await ElMessageBox.confirm("纭畾鍒犻櫎璇ユ爣绛撅紵", "鎻愮ず", { type: "warning" });
    } catch {
      return;
    }
    await deleteWatchlistTag(id);
    removeTagFromSelection(id);
    await core.fetchTags();
    ElMessage.success("鏍囩宸插垹闄?);
  }

  return {
    // 鐘舵€?    showTagManager,
    editingTagId,
    editTagName,
    editTagColor,
    selectedTagIdsForManager,
    newTagNameInManager,
    newTagColorInManager,
    editInputRef,
    presetColors: PRESET_TAG_COLORS,
    // 鍔ㄤ綔
    openTagManager,
    selectTagForEdit,
    removeTagFromSelection,
    addNewTagInManager,
    saveEditTag,
    deleteTag
  };
}
```

## `composables/watchlist/useWatchlistCore.ts`

```ts
// ============================================================================
// useWatchlistCore 鈥斺€?鑷€夎偂椤甸潰鐨勩€屽叡浜暟鎹簮銆峜omposable
// ----------------------------------------------------------------------------
// 鑱岃矗锛氭嫢鏈?items / groups / tags / realtime 绛夎法澶氫釜鍔熻兘鍏变韩鐨勭姸鎬侊紝
//       浠ュ強鎷夊彇銆佺疆椤?鏀惰棌銆佺Щ闄ゃ€佸鍑恒€佸疄鏃朵及鍊肩瓑銆屾í鍒囥€嶅姩浣溿€?// 璁捐锛歠eature composable锛堝垎缁勩€佹爣绛俱€佽繃婊ゃ€佹壒閲忥級閫氳繃鍙傛暟娉ㄥ叆 core锛?//       鎿嶄綔 core 鏆撮湶鐨?ref锛沜ore 鏈韩涓嶄緷璧栦换浣?feature composable锛?//       浠庤€岄伩鍏嶅惊鐜緷璧栥€?// 鎶界鑷?watchlist/index.vue銆?// ============================================================================
import { ref, computed, onMounted } from "vue";
import {
  getWatchlistItems,
  getWatchlistGroups,
  getWatchlistTags,
  updateWatchlistItem,
  deleteWatchlistItem,
  removeItemFromGroup
} from "@/api/watchlist";
// 瀹炴椂琛屾儏 composable锛堣矾寰勬寜椤圭洰瀹為檯浣嶇疆璋冩暣锛屽父瑙佷负 @/composables/realtime/useRealtimeQuotes锛?import { useRealtimeQuotes } from "@/composables/realtime/useRealtimeQuotes";
import { SYSTEM_GROUPS, DEFAULT_PAGE_SIZE } from "./constants";
import type {
  WatchlistItem,
  WatchlistGroup,
  WatchlistTag,
  WatchlistFetchParams,
  RemoveScope,
  RealtimeQuoteItem,
  RealtimeSummary
} from "./types";

export function useWatchlistCore() {
  // ---- 鍒楄〃鏁版嵁 ----
  const items = ref<WatchlistItem[]>([]);
  const loading = ref(false);
  const currentPage = ref(1);
  const pageSize = ref(DEFAULT_PAGE_SIZE);
  const totalItems = ref(0);

  // ---- 鍒嗙粍 / 鏍囩锛堝叡浜潵婧愶級----
  const activeGroup = ref<string | number>("all");
  const allGroups = ref<WatchlistGroup[]>([]); // 绯荤粺鍒嗙粍 + 鑷畾涔夊垎缁?  const customGroups = ref<WatchlistGroup[]>([]); // 浠呰嚜瀹氫箟鍒嗙粍
  const allTags = ref<WatchlistTag[]>([]);

  // ---- 寮瑰眰寮€鍏筹紙鍏变韩锛?---
  const showAddModal = ref(false);
  const showSettingsDrawer = ref(false);
  const removeDialogVisible = ref(false);
  const removingItem = ref<WatchlistItem | null>(null);
  const removeScope = ref<RemoveScope>("all");

  // ---- 瀹炴椂浼板€硷紙useRealtimeQuotes 宸叉槸鐙珛 composable锛屾澶勭洿鎺ユ寔鏈夛級----
  const realtime = useRealtimeQuotes({
    // 浠ュ綋鍓?items 浣滀负鎸佷粨鍠傚叆瀹炴椂琛屾儏
    getHoldings: () => items.value
  });
  const realtimeEnabled = computed(() => realtime.enabled.value);
  const toggleBtnText = computed(() => (realtimeEnabled.value ? "鍏抽棴瀹炴椂" : "寮€鍚疄鏃?));

  // --------------------------------------------------------------------------
  // 鏁版嵁鎷夊彇
  // --------------------------------------------------------------------------
  async function fetchData(params: WatchlistFetchParams = {}) {
    loading.value = true;
    try {
      const merged: WatchlistFetchParams = {
        page: currentPage.value,
        page_size: pageSize.value,
        ...params
      };
      const res = await getWatchlistItems(merged);
      // 鍏煎澶氱鍚庣杩斿洖缁撴瀯
      items.value =
        res?.items ?? res?.data ?? res?.list ?? res?.results ?? [];
      totalItems.value = res?.total ?? items.value.length;
    } finally {
      loading.value = false;
    }
  }

  async function fetchGroups() {
    const groups = (await getWatchlistGroups()) ?? [];
    customGroups.value = groups.filter((g: WatchlistGroup) => !g.is_system);
    allGroups.value = [...SYSTEM_GROUPS, ...customGroups.value];
  }

  async function fetchTags() {
    allTags.value = (await getWatchlistTags()) ?? [];
  }

  /** 鏂板鏉＄洰鍚庣殑缁熶竴鍒锋柊 */
  function onItemAdded() {
    currentPage.value = 1;
    fetchData();
    fetchGroups();
  }

  // --------------------------------------------------------------------------
  // 鏉＄洰绾у姩浣滐紙妯垏锛氳〃鏍艰 / 鎵归噺 / 鍒嗙粍閮戒細鐢ㄥ埌锛?  // --------------------------------------------------------------------------
  async function togglePin(row: WatchlistItem) {
    row.is_pinned = !row.is_pinned;
    await updateWatchlistItem(row.id, { is_pinned: row.is_pinned });
  }

  async function toggleFavorite(row: WatchlistItem) {
    row.is_favorite = !row.is_favorite;
    await updateWatchlistItem(row.id, { is_favorite: row.is_favorite });
  }

  function openRemoveDialog(row: WatchlistItem) {
    removingItem.value = row;
    removeScope.value = "all";
    removeDialogVisible.value = true;
  }

  async function executeRemove() {
    const row = removingItem.value;
    if (!row) return;
    if (removeScope.value === "all") {
      await deleteWatchlistItem(row.id);
    } else {
      const gid = typeof activeGroup.value === "number" ? activeGroup.value : null;
      if (gid != null) await removeItemFromGroup(row.id, gid);
    }
    removeDialogVisible.value = false;
    removingItem.value = null;
    currentPage.value = 1;
    fetchData();
  }

  function exportData() {
    const params = new URLSearchParams();
    if (typeof activeGroup.value === "number") {
      params.set("group_id", String(activeGroup.value));
    }
    window.open(`/api/watchlist/items/export/?${params.toString()}`);
  }

  // --------------------------------------------------------------------------
  // 瀹炴椂浼板€艰緟鍔╋紙鍖呰９ realtime锛屼緵妯℃澘 / 瀛愮粍浠惰皟鐢級
  // --------------------------------------------------------------------------
  function getValuationItem(symbol: string): RealtimeQuoteItem | undefined {
    return realtime.items.value.find((q: RealtimeQuoteItem) => q.symbol === symbol);
  }
  function getStaticPrice(symbol: string): number | undefined {
    const it = items.value.find((i) => i.symbol === symbol);
    return it?.price;
  }
  function getHoldings(): WatchlistItem[] {
    return items.value;
  }
  const realtimeSummary = computed<RealtimeSummary>(() => realtime.summary?.value ?? {});

  /** 鏍囩鍚嶆煡璇紙妯℃澘 / 瀛愮粍浠跺叡鐢級 */
  function getTagName(id: number): string {
    return allTags.value.find((t) => t.id === id)?.name ?? "";
  }
  /** 鏍囩棰滆壊鏌ヨ */
  function getTagColor(id: number): string {
    return allTags.value.find((t) => t.id === id)?.color ?? "";
  }

  // --------------------------------------------------------------------------
  // 鐢熷懡鍛ㄦ湡
  // --------------------------------------------------------------------------
  onMounted(() => {
    fetchData();
    fetchGroups();
    fetchTags();
  });

  return {
    // 鐘舵€?    items,
    loading,
    currentPage,
    pageSize,
    totalItems,
    activeGroup,
    allGroups,
    customGroups,
    allTags,
    showAddModal,
    showSettingsDrawer,
    removeDialogVisible,
    removingItem,
    removeScope,
    // 瀹炴椂
    realtime,
    realtimeEnabled,
    toggleBtnText,
    realtimeSummary,
    // 鍔ㄤ綔
    fetchData,
    fetchGroups,
    fetchTags,
    onItemAdded,
    togglePin,
    toggleFavorite,
    openRemoveDialog,
    executeRemove,
    exportData,
    getValuationItem,
    getStaticPrice,
    getHoldings,
    getTagName,
    getTagColor
  };
}
```

## `composables/watchlist/useWatchlistGroups.ts`

```ts
// ============================================================================
// useWatchlistGroups 鈥斺€?宸︿晶鍒嗙粍渚ц竟鏍忕殑 composable
// ----------------------------------------------------------------------------
// 鎶界鑷?watchlist/index.vue 鐨勩€屽垎缁勩€嶇浉鍏崇姸鎬佷笌閫昏緫锛?//   閫夋嫨鍒嗙粍銆佸唴鑱旈噸鍛藉悕銆佹柊寤哄垎缁勩€佸垹闄ゅ垎缁勩€?// 渚濊禆 core锛堝叡浜垎缁勬暟鎹簮 activeGroup / customGroups / allGroups / fetchGroups锛夈€?// ============================================================================
import { ref, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createWatchlistGroup,
  updateWatchlistGroup,
  deleteWatchlistGroup
} from "@/api/watchlist";
import type { WatchlistGroup } from "./types";

export function useWatchlistGroups(core: ReturnType<typeof import("./useWatchlistCore").useWatchlistCore>) {
  // 鍐呰仈缂栬緫鎬?  const editingGroupId = ref<number | string | null>(null);
  const editGroupName = ref("");
  // 鏂板缓鍒嗙粍寮圭獥
  const showGroupDialog = ref(false);
  const newGroupName = ref("");

  const activeGroupLabel = computed(
    () => core.allGroups.value.find((g) => g.id === core.activeGroup.value)?.name ?? "鍏ㄩ儴"
  );
  const currentIsCustom = computed(() => typeof core.activeGroup.value === "number");
  const activeCustomGroupId = computed(() =>
    currentIsCustom.value ? (core.activeGroup.value as number) : null
  );

  /**
   * 閫夋嫨鍒嗙粍銆?   * 娉ㄦ剰锛氬彧淇敼 core.activeGroup锛屼笉鍦ㄦ涓诲姩 fetchData鈥斺€?   * 鍒楄〃鍒锋柊鐢卞３缁勪欢 WatchlistIndex.vue 鐨勫崟涓€ watcher锛堢洃鍚?activeGroup + 杩囨护鍙傛暟锛夌粺涓€椹卞姩锛?   * 閬垮厤鍒嗙粍鍒囨崲涓庤繃婊ゅ彉鍖栧彔鍔犲鑷撮噸澶嶈姹傘€?   */
  function selectGroup(group: WatchlistGroup) {
    core.activeGroup.value = group.id;
    core.currentPage.value = 1;
  }

  function startEditGroup(group: WatchlistGroup) {
    editingGroupId.value = group.id;
    editGroupName.value = group.name;
  }

  function cancelEditGroup() {
    editingGroupId.value = null;
    editGroupName.value = "";
  }

  async function saveEditGroup() {
    const id = editingGroupId.value;
    if (id == null) return;
    const name = editGroupName.value.trim();
    if (!name) {
      ElMessage.warning("鍒嗙粍鍚嶄笉鑳戒负绌?);
      return;
    }
    await updateWatchlistGroup(id as number, { name });
    editingGroupId.value = null;
    editGroupName.value = "";
    await core.fetchGroups();
    ElMessage.success("鍒嗙粍宸查噸鍛藉悕");
  }

  async function deleteGroupConfirm(group: WatchlistGroup) {
    try {
      await ElMessageBox.confirm(`纭畾鍒犻櫎鍒嗙粍銆?{group.name}銆嶏紵`, "鎻愮ず", {
        type: "warning"
      });
    } catch {
      return; // 鐢ㄦ埛鍙栨秷
    }
    await deleteWatchlistGroup(group.id as number);
    // 鑻ュ垹闄ょ殑鏄綋鍓嶉€変腑鍒嗙粍锛屽洖閫€鍒般€屽叏閮ㄣ€?    if (core.activeGroup.value === group.id) {
      core.activeGroup.value = "all";
    }
    await core.fetchGroups();
    ElMessage.success("鍒嗙粍宸插垹闄?);
  }

  function handleAddGroup() {
    showGroupDialog.value = true;
    newGroupName.value = "";
  }

  async function createGroup() {
    const name = newGroupName.value.trim();
    if (!name) {
      ElMessage.warning("璇疯緭鍏ュ垎缁勫悕");
      return;
    }
    await createWatchlistGroup({ name });
    showGroupDialog.value = false;
    newGroupName.value = "";
    await core.fetchGroups();
    ElMessage.success("鍒嗙粍宸插垱寤?);
  }

  return {
    // 鐘舵€?    editingGroupId,
    editGroupName,
    showGroupDialog,
    newGroupName,
    // 娲剧敓
    activeGroupLabel,
    currentIsCustom,
    activeCustomGroupId,
    // 鍔ㄤ綔
    selectGroup,
    startEditGroup,
    cancelEditGroup,
    saveEditGroup,
    deleteGroupConfirm,
    handleAddGroup,
    createGroup
  };
}
```

## `views/asset/watchlist/WatchlistIndex.vue`

```vue
<script setup lang="ts">
// ============================================================================
// 鑷€夎偂椤甸潰锛堥噸鏋勫悗鐨勫３缁勪欢锛?// ----------------------------------------------------------------------------
// 鐢卞崟涓€ 62.6KB 鐨?watchlist/index.vue 閲嶆瀯鑰屾潵锛?//   - 鏁版嵁 / 妯垏鍔ㄤ綔 鈫?useWatchlistCore
//   - 鍒嗙粍渚ц竟鏍?     鈫?useWatchlistGroups
//   - 琛ㄦ牸杩囨护        鈫?useTableFilters
//   - 鎵归噺鎿嶄綔        鈫?useBatchActions
//   - 鏍囩绠＄悊寮圭獥    鈫?useTagManager
//   - 琛屾爣绛剧紪杈戝脊绐? 鈫?useRowTagEditor
// 鎵€鏈?composable 杩斿洖鍊肩粍瑁呬负 WatchlistContext 鍚?provide锛?// 瀛愮粍浠堕€氳繃 useWatchlistContext() 娉ㄥ叆锛岄伩鍏?prop 閫忎紶涓庨噸澶嶅疄渚嬪寲銆?// 鍒楄〃鍒锋柊缁熶竴鐢便€屽崟涓€ watcher銆嶉┍鍔紙鐩戝惉 activeGroup + 杩囨护鍙傛暟锛夈€?// ============================================================================
import { watch, provide } from "vue";
import AssetTypeBadge from "@/components/AssetTypeBadge";
import MoneyDisplay from "@/components/MoneyDisplay";
import RiseFallText from "@/components/RiseFallText";
import ProductDisplay from "@/components/ProductDisplay";
import AddToWatchlistModal from "@/components/AddToWatchlistModal.vue";
import SettingsDrawer from "@/components/SettingsDrawer.vue";

import {
  useWatchlistCore,
  useWatchlistGroups,
  useTableFilters,
  useBatchActions,
  useTagManager,
  useRowTagEditor,
  watchlistContextKey,
  VIEW_OPTIONS
} from "@/composables/watchlist";
import GroupsSidebar from "./components/GroupsSidebar.vue";
import RealtimePanel from "./components/RealtimePanel.vue";
import BatchToolbar from "./components/BatchToolbar.vue";
import TagManagerDialog from "./components/TagManagerDialog.vue";
import RowTagEditorDialog from "./components/RowTagEditorDialog.vue";

// ---- 缁勮鍏ㄩ儴 composable ----
const core = useWatchlistCore();
const filters = useTableFilters(core);
const groups = useWatchlistGroups(core);
const batch = useBatchActions(core);
const tagManager = useTagManager(core);
const rowTagEditor = useRowTagEditor(core);

// 瑙ｆ瀯鍒伴《灞傦紝渚涙ā鏉胯嚜鍔ㄨВ鍖?const {
  items,
  loading,
  currentPage,
  pageSize,
  totalItems,
  activeGroup,
  allTags,
  showAddModal,
  showSettingsDrawer,
  removeDialogVisible,
  removingItem,
  removeScope,
  togglePin,
  toggleFavorite,
  openRemoveDialog,
  executeRemove,
  exportData
} = core;
const {
  currentView,
  searchKeyword,
  currentVenueFilter,
  selectedFilterTagIds,
  venueStats,
  venueFilterOptions,
  setVenueFilter,
  handleViewChange,
  debounceSearch,
  resetFilters
} = filters;
const { activeGroupLabel } = groups;
const { batchMode, toggleBatchMode, handleSelectionChange, handleBatchDelete } = batch;
const { openTagEditor } = rowTagEditor;
const { openTagManager } = tagManager;

// ---- 鎻愪緵涓婁笅鏂?----
provide(watchlistContextKey, { core, groups, filters, batch, tagManager, rowTagEditor });

// ---- 鍗曚竴鍒锋柊 watcher锛氬垎缁勫垏鎹?+ 杩囨护鍙樺寲閮芥眹鑱氬埌杩欓噷 ----
watch(
  [() => core.activeGroup.value, () => filters.fetchParams.value],
  () => {
    core.currentPage.value = 1;
    core.fetchData({ ...filters.fetchParams.value, group: core.activeGroup.value });
  },
  { deep: true }
);
</script>

<template>
  <div class="watchlist-page flex h-full flex-col">
    <!-- 椤舵爮锛氳鍥惧垎娈?/ 鎼滅储 / 鎿嶄綔 -->
    <div class="top-bar flex items-center gap-3 border-b p-3">
      <el-radio-group :model-value="currentView" @change="handleViewChange">
        <el-radio-button v-for="opt in VIEW_OPTIONS" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </el-radio-button>
      </el-radio-group>

      <el-input
        v-model="searchKeyword"
        placeholder="鎼滅储浠ｇ爜 / 鍚嶇О"
        class="w-64"
        clearable
        @input="debounceSearch"
      />

      <div class="ml-auto flex items-center gap-2">
        <el-button :type="batchMode ? 'primary' : 'default'" @click="toggleBatchMode">
          {{ batchMode ? "鎵归噺妯″紡" : "杩涘叆鎵归噺" }}
        </el-button>
        <el-button @click="openTagManager">绠＄悊鏍囩</el-button>
        <el-button @click="exportData">瀵煎嚭</el-button>
        <el-button @click="showSettingsDrawer = true">璁剧疆</el-button>
        <el-button type="primary" @click="showAddModal = true">+ 娣诲姞</el-button>
      </div>
    </div>

    <!-- 涓讳綋锛氬乏鍒嗙粍 + 鍙宠〃鏍?-->
    <div class="flex flex-1 gap-0 overflow-hidden">
      <GroupsSidebar />

      <div class="flex-1 overflow-auto p-3">
        <RealtimePanel />
        <BatchToolbar />

        <!-- 杩囨护鏍?-->
        <div class="mb-2 flex items-center gap-3">
          <div class="venue-filter flex gap-1">
            <el-button
              v-for="opt in venueFilterOptions"
              :key="opt.value"
              size="small"
              :type="currentVenueFilter === opt.value ? 'primary' : 'default'"
              @click="setVenueFilter(opt.value)"
            >
              {{ opt.label }}{{ venueStats[opt.value] != null ? `(${venueStats[opt.value]})` : "" }}
            </el-button>
          </div>
          <el-select
            v-model="selectedFilterTagIds"
            multiple
            collapse-tags
            placeholder="鎸夋爣绛剧瓫閫?
            class="w-56"
          >
            <el-option
              v-for="t in allTags"
              :key="t.id"
              :label="t.name"
              :value="t.id"
            />
          </el-select>
          <el-button text size="small" @click="resetFilters">閲嶇疆</el-button>
          <span class="ml-auto text-sm text-gray-500">{{ activeGroupLabel }}</span>
        </div>

        <!-- 琛ㄦ牸 -->
        <el-table
          v-loading="loading"
          :data="items"
          row-key="id"
          @selection-change="handleSelectionChange"
        >
          <el-table-column v-if="batchMode" type="selection" width="48" />
          <el-table-column label="浜у搧">
            <template #default="{ row }">
              <ProductDisplay :code="row.code" :name="row.name" />
            </template>
          </el-table-column>
          <el-table-column label="绫诲瀷" width="90">
            <template #default="{ row }">
              <AssetTypeBadge :asset-type="row.asset_type" :venue="row.venue" />
            </template>
          </el-table-column>
          <el-table-column label="鏈€鏂颁环" width="110">
            <template #default="{ row }">
              <MoneyDisplay :value="row.price" />
            </template>
          </el-table-column>
          <el-table-column label="娑ㄨ穼骞? width="100">
            <template #default="{ row }">
              <RiseFallText :value="row.change_percent" />
            </template>
          </el-table-column>
          <el-table-column label="鏍囩">
            <template #default="{ row }">
              <el-tag
                v-for="tid in row.tags || []"
                :key="tid"
                size="small"
                class="mr-1"
              >
                {{ core.getTagName(tid) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="鎿嶄綔" width="220" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" @click="togglePin(row)">
                {{ row.is_pinned ? "鍙栨秷缃《" : "缃《" }}
              </el-button>
              <el-button text size="small" @click="toggleFavorite(row)">
                {{ row.is_favorite ? "鍙栨秷鏀惰棌" : "鏀惰棌" }}
              </el-button>
              <el-button text size="small" @click="openTagEditor(row)">鏍囩</el-button>
              <el-button text size="small" type="danger" @click="openRemoveDialog(row)">
                绉婚櫎
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="mt-3 flex justify-end">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="totalItems"
            layout="total, prev, pager, next"
          />
        </div>
      </div>
    </div>

    <!-- 寮瑰眰 -->
    <AddToWatchlistModal v-model="showAddModal" @added="core.onItemAdded" />
    <SettingsDrawer v-model="showSettingsDrawer" />
    <TagManagerDialog />
    <RowTagEditorDialog />

    <!-- 绉婚櫎纭 -->
    <el-dialog v-model="removeDialogVisible" title="绉婚櫎鑷€? width="360px">
      <el-radio-group v-model="removeScope">
        <el-radio value="all">浠庡叏閮ㄧЩ闄?/el-radio>
        <el-radio value="current">浠呬粠褰撳墠鍒嗙粍绉婚櫎</el-radio>
      </el-radio-group>
      <template #footer>
        <el-button @click="removeDialogVisible = false">鍙栨秷</el-button>
        <el-button type="primary" @click="executeRemove">纭畾</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.watchlist-page {
  background: var(--el-bg-color);
}
</style>
```

## `views/asset/watchlist/components/BatchToolbar.vue`

```vue
<script setup lang="ts">
// 鎵归噺鎿嶄綔宸ュ叿鏍忥紙鎶界鑷?watchlist/index.vue 鎵归噺妯″紡鎸夐挳鍖猴級
// 鍦ㄥ３缁勪欢妯℃澘涓簬 batchMode 涓虹湡鏃舵覆鏌撱€?import { useWatchlistContext } from "@/composables/watchlist";

const { core, batch } = useWatchlistContext();
const { customGroups } = core;
const {
  batchMode,
  selectedItems,
  batchMoveGroupId,
  toggleBatchMode,
  handleBatchDelete,
  handleBatchMoveToGroup
} = batch;

function onMove() {
  if (batchMoveGroupId.value != null) {
    handleBatchMoveToGroup(Number(batchMoveGroupId.value));
  }
}
</script>

<template>
  <div v-if="batchMode" class="batch-toolbar flex items-center gap-2 rounded bg-primary-light p-2">
    <span class="text-sm">宸查€?{{ selectedItems.length }} 椤?/span>
    <el-select v-model="batchMoveGroupId" placeholder="绉诲姩鍒板垎缁? size="small" class="w-36">
      <el-option
        v-for="g in customGroups"
        :key="String(g.id)"
        :label="g.name"
        :value="g.id"
      />
    </el-select>
    <el-button size="small" @click="onMove">绉诲姩</el-button>
    <el-button size="small" type="danger" @click="handleBatchDelete">鍒犻櫎</el-button>
    <el-button size="small" text @click="toggleBatchMode">閫€鍑烘壒閲?/el-button>
  </div>
</template>

<style scoped>
.batch-toolbar {
  background: var(--el-color-primary-light-9);
}
</style>
```

## `views/asset/watchlist/components/GroupsSidebar.vue`

```vue
<script setup lang="ts">
// 宸︿晶鍒嗙粍渚ц竟鏍忥紙鎶界鑷?watchlist/index.vue 宸︽爮锛?// 閫氳繃 useWatchlistContext 娉ㄥ叆 core + groups锛岄伩鍏?prop 閫忎紶銆?import { Edit, Delete, Plus } from "@element-plus/icons-vue";
import { useWatchlistContext } from "@/composables/watchlist";

const { core, groups } = useWatchlistContext();
// 瑙ｆ瀯涓洪《灞?ref / 鍑芥暟锛屾ā鏉夸腑鑷姩瑙ｅ寘锛坮ef 鑷姩鎷嗗€硷紝鍑芥暟鍙洿鎺ヨ皟鐢級
const { activeGroup, allGroups } = core;
const {
  editingGroupId,
  editGroupName,
  showGroupDialog,
  newGroupName,
  selectGroup,
  startEditGroup,
  saveEditGroup,
  deleteGroupConfirm,
  handleAddGroup,
  createGroup
} = groups;
</script>

<template>
  <aside class="w-56 shrink-0 border-r p-3">
    <div class="mb-2 flex items-center justify-between">
      <span class="font-medium">鍒嗙粍</span>
      <el-button text :icon="Plus" @click="handleAddGroup" />
    </div>

    <ul class="space-y-1">
      <li
        v-for="g in allGroups"
        :key="String(g.id)"
        class="group-item flex cursor-pointer items-center justify-between rounded px-2 py-1.5 text-sm"
        :class="{ 'is-active': activeGroup === g.id }"
        @click="selectGroup(g)"
      >
        <template v-if="editingGroupId === g.id">
          <el-input
            v-model="editGroupName"
            size="small"
            class="flex-1"
            @click.stop
            @keyup.enter="saveEditGroup"
            @blur="saveEditGroup"
          />
        </template>
        <template v-else>
          <span class="truncate">{{ g.name }}</span>
          <span v-if="!g.is_system" class="actions opacity-0 group-hover:opacity-100">
            <el-icon class="hover:text-primary" @click.stop="startEditGroup(g)">
              <Edit />
            </el-icon>
            <el-icon class="hover:text-danger" @click.stop="deleteGroupConfirm(g)">
              <Delete />
            </el-icon>
          </span>
        </template>
      </li>
    </ul>

    <!-- 鏂板缓鍒嗙粍 -->
    <el-dialog v-model="showGroupDialog" title="鏂板缓鍒嗙粍" width="360px">
      <el-input v-model="newGroupName" placeholder="璇疯緭鍏ュ垎缁勫悕" @keyup.enter="createGroup" />
      <template #footer>
        <el-button @click="showGroupDialog = false">鍙栨秷</el-button>
        <el-button type="primary" @click="createGroup">纭畾</el-button>
      </template>
    </el-dialog>
  </aside>
</template>

<style scoped>
.group-item.is-active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.group-item .actions {
  display: inline-flex;
  gap: 6px;
}
</style>
```

## `views/asset/watchlist/components/RealtimePanel.vue`

```vue
<script setup lang="ts">
// 瀹炴椂浼板€奸潰鏉匡紙鎶界鑷?watchlist/index.vue 鐨勫疄鏃惰鎯呭尯鍧楋級
// 澶嶇敤椤圭洰宸叉湁鐨?RealtimeWarningBanner / RealtimeStatusIndicator 瀛愮粍浠躲€?import RealtimeWarningBanner from "@/components/RealtimeWarningBanner.vue";
import RealtimeStatusIndicator from "@/components/RealtimeStatusIndicator.vue";
import { useWatchlistContext } from "@/composables/watchlist";

const { core } = useWatchlistContext();
const { realtime, toggleBtnText, realtimeSummary } = core;
// realtime 鍐呴儴涓?ref锛岃В鏋勫埌椤跺眰浠ュ湪妯℃澘鑷姩瑙ｅ寘
const { enabled, status, lastUpdateTime } = realtime;
</script>

<template>
  <section class="realtime-panel mb-3 rounded border p-3">
    <RealtimeWarningBanner v-if="!enabled" />

    <div class="flex items-center justify-between">
      <RealtimeStatusIndicator
        :enabled="enabled"
        :status="status"
        :last-update-time="lastUpdateTime"
      />
      <el-button size="small" @click="realtime.toggle()">
        {{ toggleBtnText }}
      </el-button>
    </div>

    <div class="mt-2 grid grid-cols-3 gap-3 text-sm">
      <div>
        <div class="text-gray-500">鎬诲競鍊?/div>
        <div class="font-medium">{{ realtimeSummary.totalMarketValue ?? "鈥? }}</div>
      </div>
      <div>
        <div class="text-gray-500">鎬绘敹鐩?/div>
        <div class="font-medium">{{ realtimeSummary.totalProfit ?? "鈥? }}</div>
      </div>
      <div>
        <div class="text-gray-500">鏀剁泭鐜?/div>
        <div class="font-medium">{{ realtimeSummary.totalProfitPercent ?? "鈥? }}%</div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.realtime-panel {
  background: var(--el-fill-color-light);
}
</style>
```

## `views/asset/watchlist/components/RowTagEditorDialog.vue`

```vue
<script setup lang="ts">
// 鍗曡鏍囩缂栬緫寮圭獥锛堟娊绂昏嚜 watchlist/index.vue 鐨勩€岀紪杈戞爣绛俱€嶅璇濇锛?import { useWatchlistContext } from "@/composables/watchlist";

const { core, rowTagEditor } = useWatchlistContext();
const { allTags, getTagName, getTagColor } = core;
const {
  showTagEditor,
  editingItem,
  editingItemNewTagIds,
  savingTags,
  showNewTagFormInEditor,
  newTagNameInEditor,
  newTagColorInEditor,
  presetColors,
  availableTagsForEditor,
  removeTagFromEditingItem,
  createTagInEditor,
  saveTagChanges
} = rowTagEditor;
</script>

<template>
  <el-dialog v-model="showTagEditor" title="缂栬緫鏍囩" width="440px">
    <div v-if="editingItem" class="space-y-3">
      <div class="text-sm text-gray-500">
        鏍囩殑锛?span class="font-medium text-gray-800">{{ editingItem.name }}</span>
      </div>

      <!-- 宸查€夋爣绛?-->
      <div class="flex flex-wrap gap-2">
        <el-tag
          v-for="id in editingItemNewTagIds"
          :key="id"
          :color="getTagColor(id)"
          closable
          @close="removeTagFromEditingItem(id)"
        >
          {{ getTagName(id) }}
        </el-tag>
        <span v-if="!editingItemNewTagIds.length" class="text-sm text-gray-400">鏆傛棤鏍囩</span>
      </div>

      <!-- 閫夋嫨鍙敤鏍囩 -->
      <el-select
        v-model="editingItemNewTagIds"
        multiple
        filterable
        placeholder="閫夋嫨鏍囩"
        class="w-full"
      >
        <el-option
          v-for="t in availableTagsForEditor"
          :key="t.id"
          :label="t.name"
          :value="t.id"
        />
      </el-select>

      <!-- 琛屽唴鏂板缓鏍囩 -->
      <div v-if="showNewTagFormInEditor" class="flex items-center gap-2">
        <el-input v-model="newTagNameInEditor" size="small" placeholder="鏂版爣绛惧悕" class="flex-1" />
        <div class="flex gap-1">
          <span
            v-for="c in presetColors"
            :key="c"
            class="h-4 w-4 cursor-pointer rounded-full"
            :style="{ background: c }"
            :class="{ ring: newTagColorInEditor === c }"
            @click="newTagColorInEditor = c"
          />
        </div>
        <el-button size="small" type="primary" @click="createTagInEditor">鏂板缓</el-button>
      </div>
      <el-button v-else text type="primary" size="small" @click="showNewTagFormInEditor = true">
        + 鏂板缓鏍囩
      </el-button>
    </div>

    <template #footer>
      <el-button @click="showTagEditor = false">鍙栨秷</el-button>
      <el-button type="primary" :loading="savingTags" @click="saveTagChanges">淇濆瓨</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.ring {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 1px;
}
</style>
```

## `views/asset/watchlist/components/TagManagerDialog.vue`

```vue
<script setup lang="ts">
// 鍏ㄥ眬鏍囩绠＄悊寮圭獥锛堟娊绂昏嚜 watchlist/index.vue 鐨勩€岀鐞嗘爣绛俱€嶅璇濇锛?import { useWatchlistContext } from "@/composables/watchlist";

const { core, tagManager } = useWatchlistContext();
const { allTags, getTagName, getTagColor } = core;
const {
  showTagManager,
  editingTagId,
  editTagName,
  editTagColor,
  newTagNameInManager,
  newTagColorInManager,
  presetColors,
  selectTagForEdit,
  removeTagFromSelection,
  addNewTagInManager,
  saveEditTag,
  deleteTag
} = tagManager;
</script>

<template>
  <el-dialog v-model="showTagManager" title="绠＄悊鏍囩" width="480px">
    <!-- 鏍囩鍒楄〃 -->
    <ul class="space-y-2">
      <li
        v-for="tag in allTags"
        :key="tag.id"
        class="flex items-center gap-2 rounded border px-2 py-1.5"
      >
        <span class="inline-block h-3 w-3 rounded-full" :style="{ background: tag.color }" />
        <template v-if="editingTagId === tag.id">
          <el-input v-model="editTagName" size="small" class="flex-1" />
          <div class="flex gap-1">
            <span
              v-for="c in presetColors"
              :key="c"
              class="h-4 w-4 cursor-pointer rounded-full"
              :style="{ background: c }"
              :class="{ ring: editTagColor === c }"
              @click="editTagColor = c"
            />
          </div>
          <el-button size="small" type="primary" @click="saveEditTag(tag.id)">淇濆瓨</el-button>
        </template>
        <template v-else>
          <span class="flex-1">{{ tag.name }}</span>
          <el-button text size="small" @click="selectTagForEdit(tag.id)">缂栬緫</el-button>
          <el-button text size="small" type="danger" @click="deleteTag(tag.id)">鍒犻櫎</el-button>
        </template>
      </li>
    </ul>

    <!-- 鏂板缓鏍囩 -->
    <div class="mt-3 flex items-center gap-2 border-t pt-3">
      <el-input v-model="newTagNameInManager" size="small" placeholder="鏂版爣绛惧悕" class="flex-1" />
      <div class="flex gap-1">
        <span
          v-for="c in presetColors"
          :key="c"
          class="h-4 w-4 cursor-pointer rounded-full"
          :style="{ background: c }"
          :class="{ ring: newTagColorInManager === c }"
          @click="newTagColorInManager = c"
        />
      </div>
      <el-button size="small" type="primary" @click="addNewTagInManager">娣诲姞</el-button>
    </div>
  </el-dialog>
</template>

<style scoped>
.ring {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 1px;
}
</style>
```
