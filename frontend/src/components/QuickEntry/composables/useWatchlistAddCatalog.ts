// 「添加自选」弹窗的分组 / 标签目录（#980 拆分自 AddToWatchlistModal.vue）。
//
// 只负责目录：拉取、本地新建项的并集合并（#2106 后续：新建后下拉看不到）、
// 行内「+」新建成功后的选中回填。提交与脏检查留在组件里。
//
// 为什么并集而不是直接覆盖：新建成功后立即重拉列表，但这次拉取不保证带上刚建的那条
// （写请求在响应返回后才提交、请求抖动、列表截断），一旦响应里没有它，用户刚建的标签
// 就从下拉里消失——而弹窗其实已经握有这个对象。
import { computed, onMounted, ref, type Ref } from "vue";
import {
  getWatchlistGroups,
  getWatchlistTags,
  type WatchlistGroup,
  type WatchlistTag
} from "@/api/watchlist";

export interface UseWatchlistAddCatalogOptions {
  /** 打开弹窗时默认勾选的分组（从某个自定义分组里点「添加自选」进来） */
  initialGroupId: Ref<number | undefined>;
  /** 目录变更（新建 / 编辑了标签或分组）→ 通知父页面刷新全局目录 */
  onCatalogChanged?: () => void;
}

export function useWatchlistAddCatalog(options: UseWatchlistAddCatalogOptions) {
  const { initialGroupId, onCatalogChanged } = options;
  const notifyCatalogChanged = () => onCatalogChanged?.();

  const availableGroups = ref<WatchlistGroup[]>([]);
  const selectedGroupIds = ref<number[]>([]);

  const availableTags = ref<WatchlistTag[]>([]);
  const selectedTagIds = ref<number[]>([]);

  const tagFormUsedColors = computed(() =>
    availableTags.value.map(t => t.color).filter((c): c is string => !!c)
  );
  const groupFormUsedColors = computed(() =>
    availableGroups.value.map(g => g.color).filter((c): c is string => !!c)
  );

  // 本弹窗内新建成功的标签（#2106 后续：新建后下拉看不到）。
  // 背景：新建成功后会立刻重新拉取标签列表并**整体替换** availableTags，而这次
  // 拉取并不保证带上刚建的标签（写请求在响应返回后才提交、请求抖动、列表截断等），
  // 一旦响应里没有它，用户刚建的标签就从下拉里消失了——而弹窗其实已经握有这个对象。
  // 故刷新时按 id 做**并集**：本地新建的标签永不因重新拉取而掉出下拉。
  const locallyCreatedTags = ref<WatchlistTag[]>([]);

  /** 服务端列表 ⊕ 本地新建标签（同 id 以服务端为准，保留服务端排序在前） */
  function mergeLocalTags(list: WatchlistTag[]): WatchlistTag[] {
    const merged = [...list];
    const known = new Set(merged.map(t => t.id));
    for (const t of locallyCreatedTags.value) {
      if (!known.has(t.id)) merged.push(t);
    }
    return merged;
  }

  // 新建标签成功：直接并入可选项并自动选中，免去内联表单
  const onTagFormCreated = (tag: WatchlistTag) => {
    if (!locallyCreatedTags.value.find(t => t.id === tag.id)) {
      locallyCreatedTags.value.push(tag);
    }
    if (!availableTags.value.find(t => t.id === tag.id)) {
      availableTags.value.push(tag);
    }
    if (!selectedTagIds.value.includes(tag.id)) {
      selectedTagIds.value.push(tag.id);
    }
    notifyCatalogChanged();
  };
  // 编辑 / 其他变更：兜底刷新标签列表，保持与全局一致
  const onTagFormSaved = () => {
    fetchTags();
    notifyCatalogChanged();
  };

  // 新建分组成功：并入可选项并自动选中（与标签同款：本地新建项不因刷新掉出下拉）
  const locallyCreatedGroups = ref<WatchlistGroup[]>([]);

  /** 服务端分组 ⊕ 本地新建分组（同 id 以服务端为准） */
  function mergeLocalGroups(list: WatchlistGroup[]): WatchlistGroup[] {
    const merged = [...list];
    const known = new Set(merged.map(g => g.id));
    for (const g of locallyCreatedGroups.value) {
      if (!known.has(g.id)) merged.push(g);
    }
    return merged;
  }

  const onGroupFormCreated = (group: WatchlistGroup) => {
    if (!locallyCreatedGroups.value.find(g => g.id === group.id)) {
      locallyCreatedGroups.value.push(group);
    }
    if (!availableGroups.value.find(g => g.id === group.id)) {
      availableGroups.value.push(group);
    }
    if (!selectedGroupIds.value.includes(group.id)) {
      selectedGroupIds.value.push(group.id);
    }
    notifyCatalogChanged();
  };
  const onGroupFormSaved = () => {
    fetchGroups();
    notifyCatalogChanged();
  };

  const fetchGroups = async () => {
    try {
      const res = await getWatchlistGroups();
      const allGroups: WatchlistGroup[] = res.data ?? [];
      availableGroups.value = mergeLocalGroups(
        allGroups.filter(g => !g.is_system && g.id != null)
      );
    } catch (e) {
      console.error("获取分组失败：", e);
    }
  };

  const fetchTags = async () => {
    try {
      const res = await getWatchlistTags();
      const serverTags = (res.data ?? []).map((tag: WatchlistTag) => ({
        ...tag,
        color: tag.color || "var(--text-disabled)"
      }));
      // 并集而非覆盖：本地新建的标签不因这次拉取而掉出下拉（#2106 后续）
      availableTags.value = mergeLocalTags(serverTags);
    } catch (e) {
      console.error("获取标签失败：", e);
    }
  };

  /**
   * 选中一条资产后的默认勾选：默认进「来源分组」，标签清空。
   * 与 resetForm 的「一律清空」区分开——后者回到「没有任何预设」的初始态。
   */
  function applyInitialSelection() {
    selectedGroupIds.value = initialGroupId.value ? [initialGroupId.value] : [];
    selectedTagIds.value = [];
  }

  onMounted(async () => {
    await fetchTags();
    await fetchGroups();
  });

  return {
    availableGroups,
    availableTags,
    selectedGroupIds,
    selectedTagIds,
    tagFormUsedColors,
    groupFormUsedColors,
    fetchGroups,
    fetchTags,
    onTagFormCreated,
    onTagFormSaved,
    onGroupFormCreated,
    onGroupFormSaved,
    applyInitialSelection
  };
}
