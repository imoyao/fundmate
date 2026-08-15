import { ref } from "vue";
import { getWatchlistTags, type WatchlistTag } from "@/api/watchlist";

/**
 * 自选标签状态与筛选逻辑（从 watchlist/index.vue 抽离，2026-08-15）。
 * 负责标签列表、标签筛选面板（触发按钮 + Checkbox）的状态与 fetch。
 * 筛选确定/清空后通过 refresh 回调触发列表刷新（解耦 fetchData，避免循环依赖）。
 *
 * @param refresh 筛选提交后执行的刷新动作（一般为 `() => { currentPage.value = 1; fetchData(); }`）
 */
export function useWatchlistTags(refresh?: () => void) {
  const allTags = ref<WatchlistTag[]>([]);
  // 已生效的标签筛选条件
  const selectedFilterTagIds = ref<number[]>([]);
  // 弹出面板可见性
  const tagFilterVisible = ref(false);
  // 面板内草稿选择，确定后才提交到 selectedFilterTagIds（避免每次勾选即时触发筛选）
  const draftFilterTagIds = ref<number[]>([]);

  async function fetchTags() {
    try {
      const res = await getWatchlistTags();
      allTags.value = res.data ?? [];
    } catch (e) {
      console.error("获取标签失败：", e);
    }
  }

  // 打开筛选面板时同步草稿，使未提交的勾选与已生效的筛选保持一致
  function onTagFilterShow() {
    draftFilterTagIds.value = [...selectedFilterTagIds.value];
  }

  // 确定：提交草稿并触发筛选
  function applyTagFilter() {
    selectedFilterTagIds.value = [...draftFilterTagIds.value];
    tagFilterVisible.value = false;
    refresh?.();
  }

  // 清空：移除全部标签筛选并关闭面板
  function clearTagFilter() {
    selectedFilterTagIds.value = [];
    draftFilterTagIds.value = [];
    tagFilterVisible.value = false;
    refresh?.();
  }

  // 仅重置选中态（不触发刷新），供外层 resetFilters 组合使用
  function resetTagFilter() {
    selectedFilterTagIds.value = [];
    draftFilterTagIds.value = [];
    tagFilterVisible.value = false;
  }

  return {
    allTags,
    selectedFilterTagIds,
    tagFilterVisible,
    draftFilterTagIds,
    fetchTags,
    onTagFilterShow,
    applyTagFilter,
    clearTagFilter,
    resetTagFilter
  };
}
