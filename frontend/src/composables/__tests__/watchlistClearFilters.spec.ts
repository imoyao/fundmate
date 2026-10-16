/**
 * #2199 ⑥「清除筛选」一键快捷：useWatchlistData.clearAllFilters 的状态复位与刷新分流。
 *
 * 重点钉住三条刷新路径的路由语义（与 index.vue 的 watch 接线一一对应）：
 * - 只清类型（分组已在「全部」、标签本就空）→ 无人 watch 兜底，必须显式 fetch；
 * - 标签由非空清空 → composable 内 watch(selectedFilterTagIds) 兜底 fetch；
 * - 分组偏离「全部」→ 切回 "all"（不是 holding），刷新由 index.vue watch(activeGroup)
 *   兜底——composable 单测里没有那条 watch，故断言「本函数不显式 fetch」。
 */
import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import { useWatchlistTags } from "@/composables/useWatchlistTags";
import {
  useWatchlistData,
  type WatchlistToolbarState
} from "@/composables/useWatchlistData";
import type { WatchlistItem } from "@/api/watchlist";

const m = vi.hoisted(() => ({
  getItems: vi.fn(),
  getGroups: vi.fn(),
  getTags: vi.fn(),
  updateItem: vi.fn(),
  deleteItem: vi.fn(),
  removeItemFromGroup: vi.fn(),
  addItemToGroup: vi.fn()
}));

vi.mock("@/api/watchlist", () => ({
  getWatchlistItems: m.getItems,
  getWatchlistGroups: m.getGroups,
  getWatchlistTags: m.getTags,
  updateWatchlistItem: m.updateItem,
  deleteWatchlistItem: m.deleteItem,
  removeItemFromGroup: m.removeItemFromGroup,
  addItemToGroup: m.addItemToGroup
}));
// node 环境无 DOM：element-plus 只取到用到的两个消息入口，其余不加载
vi.mock("element-plus", () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() }
}));
vi.mock("@/utils/localforage", () => ({
  localForage: () => ({ getItem: vi.fn(), setItem: vi.fn() })
}));

/** 最小 toolbar 状态（useWatchlistToolbar 的形状，纯 ref 集合无行为） */
function makeToolbar(): WatchlistToolbarState {
  return {
    searchKeyword: ref(""),
    currentView: ref("all"),
    selectedAssetTypes: ref<string[]>([]),
    batchMode: ref(false),
    selectedItems: ref<WatchlistItem[]>([]),
    batchMoveGroupId: ref(undefined)
  };
}

/** 等 watch（pre-flush）与 fetchData 的 Promise 链全部落地 */
function flush() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

beforeEach(() => {
  vi.clearAllMocks();
  m.getItems.mockResolvedValue({ data: [], total: 0 });
});

describe("clearAllFilters（#2199 ⑥ 清除筛选）", () => {
  it("只清类型（分组已在全部、标签本就空）→ 显式刷新，搜索词不动", async () => {
    const groups = useWatchlistGroups();
    const tags = useWatchlistTags();
    const toolbar = makeToolbar();
    const data = useWatchlistData(groups, tags, toolbar);
    groups.activeGroup.value = "all";
    toolbar.selectedAssetTypes.value = ["manager"];
    toolbar.searchKeyword.value = "茅台";
    await flush();
    m.getItems.mockClear();

    data.clearAllFilters();
    await flush();

    expect(toolbar.selectedAssetTypes.value).toEqual([]);
    expect(groups.activeGroup.value).toBe("all");
    expect(toolbar.searchKeyword.value).toBe("茅台"); // 搜索框不在清除范围
    expect(data.currentPage.value).toBe(1);
    // 无人兜底的场景：本函数显式发起刷新（用户实测「条件残留」的根因路径）
    expect(m.getItems).toHaveBeenCalled();
  });

  it("标签非空 → 复位标签并由 watch 兜底刷新（类型同步清空）", async () => {
    const groups = useWatchlistGroups();
    const tags = useWatchlistTags();
    const toolbar = makeToolbar();
    const data = useWatchlistData(groups, tags, toolbar);
    groups.activeGroup.value = "all";
    tags.selectedFilterTagIds.value = [1, 2];
    toolbar.selectedAssetTypes.value = ["stock"];
    await flush();
    m.getItems.mockClear();

    data.clearAllFilters();
    await flush();

    expect(tags.selectedFilterTagIds.value).toEqual([]);
    expect(toolbar.selectedAssetTypes.value).toEqual([]);
    expect(m.getItems).toHaveBeenCalled();
  });

  it("分组偏离「全部」→ 切回 all（不是 holding），本函数不显式 fetch", async () => {
    const groups = useWatchlistGroups();
    const tags = useWatchlistTags();
    const toolbar = makeToolbar();
    const data = useWatchlistData(groups, tags, toolbar);
    groups.activeGroup.value = "custom_3";
    toolbar.selectedAssetTypes.value = ["etf"];
    await flush();
    m.getItems.mockClear();

    data.clearAllFilters();
    await flush();

    // 回「全部」而非 resetActiveGroup 的 holding（#2199 明确的坑）
    expect(groups.activeGroup.value).toBe("all");
    expect(toolbar.selectedAssetTypes.value).toEqual([]);
    // 分组切换的刷新由 index.vue watch(activeGroup) 兜底；composable 内不重复发起
    expect(m.getItems).not.toHaveBeenCalled();
  });

  it("分组本就是 holding、只清类型 → holding 切到 all 由分组 watch 兜底，不显式 fetch", async () => {
    const groups = useWatchlistGroups();
    const tags = useWatchlistTags();
    const toolbar = makeToolbar();
    const data = useWatchlistData(groups, tags, toolbar);
    // activeGroup 默认即 holding（useWatchlistGroups 初始值）
    toolbar.selectedAssetTypes.value = ["fund"];
    await flush();
    m.getItems.mockClear();

    data.clearAllFilters();
    await flush();

    // holding → all 属分组变化：刷新职责在 index.vue 的 watch，composable 内不双发
    expect(groups.activeGroup.value).toBe("all");
    expect(m.getItems).not.toHaveBeenCalled();
  });
});
