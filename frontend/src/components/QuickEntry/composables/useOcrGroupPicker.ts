/**
 * 导入时的分组选择（#2106，#980 拆分产物）。
 *
 * 归属说明：只列**自定义分组**（多对多真实关联）；「全部」等系统分组是虚拟口径、
 * 没有关联关系，故不作为勾选项出现——用户需要感知的是「可补救」，
 * 而不是「全部不可取消」（后者等于发明一个不存在的状态）。
 */

import { computed, ref } from "vue";
import { getWatchlistGroups, type WatchlistGroup } from "@/api/watchlist";

export function useOcrGroupPicker() {
  const availableGroups = ref<WatchlistGroup[]>([]);
  const selectedGroupIds = ref<number[]>([]);

  /** 已占用的分组色，供新建分组弹窗随机取色时避开 */
  const groupFormUsedColors = computed<string[]>(() =>
    availableGroups.value
      .map(g => g.color)
      .filter((c): c is string => Boolean(c))
  );

  async function fetchGroups(): Promise<void> {
    try {
      const res = await getWatchlistGroups();
      availableGroups.value = (res.data ?? []).filter(
        g => !g.is_system && g.id != null
      );
    } catch (e) {
      console.error("获取分组失败：", e);
    }
  }

  /** 现场新建的分组直接补进可选项并选中，省得用户再找一遍 */
  function onGroupCreated(group: WatchlistGroup): void {
    if (group.id == null) return;
    if (!availableGroups.value.some(g => g.id === group.id)) {
      availableGroups.value = [...availableGroups.value, group];
    }
    if (!selectedGroupIds.value.includes(group.id)) {
      selectedGroupIds.value = [...selectedGroupIds.value, group.id];
    }
  }

  function resetGroupSelection(): void {
    selectedGroupIds.value = [];
  }

  return {
    availableGroups,
    selectedGroupIds,
    groupFormUsedColors,
    fetchGroups,
    onGroupCreated,
    resetGroupSelection
  };
}
