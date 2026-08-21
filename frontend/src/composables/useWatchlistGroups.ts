import { ref, computed } from "vue";
import { getWatchlistGroups, type WatchlistGroup } from "@/api/watchlist";
import { SYSTEM_GROUPS } from "@/constants/watchlist";

/** 分组 Tab 展示项（系统 + 自定义归一化）。原定义在 watchlist/index.vue，现收敛至此 composable。 */
export interface GroupTab {
  key: string;
  label: string;
  color: string | null;
  count: number;
  filter: Record<string, string | number | boolean>;
}

/** 系统分组过滤映射（方案 B：场内/场外已由顶部 el-segmented 承担，不在分组 tab 内）。 */
function getSystemFilter(key: string): Record<string, string | boolean> {
  const map: Record<string, Record<string, string | boolean>> = {
    all: {},
    holding: { status: "HOLDING" },
    watching: { status: "WATCHING" },
    cleared: { status: "cleared" },
    exchange: { venue: "EXCHANGE" },
    otc: { venue: "OTC" },
    favorite: { favorite: true }
  };
  return map[key] || {};
}

/**
 * 自选分组状态与数据逻辑（从 watchlist/index.vue 抽离，2026-08-15）。
 * 仅负责分组 tab 的派生态与 fetch，不耦合列表请求 fetchData——
 * 分组切换的刷新由组件内 watch(activeGroup) 负责，故本 composable 不接收 refresh 回调。
 */
export function useWatchlistGroups() {
  const activeGroup = ref("holding");
  const allGroups = ref<GroupTab[]>([]);
  const customGroups = ref<WatchlistGroup[]>([]);
  /** 分组管理弹窗用：系统分组（无 id 只有 key，可见不可编辑/删除）+ 自定义分组（原样含 id） */
  const managerGroups = ref<WatchlistGroup[]>([]);

  const activeGroupLabel = computed(() => {
    const group = allGroups.value.find(g => g.key === activeGroup.value);
    return group?.label || "全部";
  });

  const currentIsCustom = computed(() =>
    activeGroup.value.startsWith("custom_")
  );

  const activeCustomGroupId = computed(() => {
    if (currentIsCustom.value) {
      const idStr = activeGroup.value.replace("custom_", "");
      return /^\d+$/.test(idStr) ? parseInt(idStr) : undefined;
    }
    return undefined;
  });

  async function fetchGroups() {
    try {
      const res = await getWatchlistGroups();
      const data: WatchlistGroup[] = res.data ?? [];
      const system: GroupTab[] = [];
      const custom: WatchlistGroup[] = [];
      const manager: WatchlistGroup[] = [];
      data.forEach(g => {
        // 方案 B：后端仍返回 exchange/otc 系统分组，但「场内/场外」已由顶部 el-segmented 承担，此处过滤不展示
        if (g.is_system && (g.key === "exchange" || g.key === "otc")) return;
        if (g.is_system) {
          // 系统默认组无数据不展示（「全部」始终展示）；自定义组 count=0 保持现状
          if (g.key !== "all" && (g.count || 0) === 0) return;
          system.push({
            key: g.key!,
            label: g.label || g.name || g.key,
            color: g.color,
            count: g.count || 0,
            filter: getSystemFilter(g.key!)
          });
          // 管理弹窗系统分组行：无自选 id（undefined），编辑/删除被禁用
          manager.push({
            id: undefined,
            key: g.key!,
            name: g.label || g.name || g.key,
            color: g.color,
            count: g.count || 0,
            is_system: true,
            is_visible: true,
            entity_type: "ASSET"
          });
        } else {
          custom.push(g);
          manager.push(g); // 自定义分组原样（含 id，可编辑/删除）
          system.push({
            key: `custom_${g.id}`,
            label: g.name,
            color: g.color || SYSTEM_GROUPS[0].color,
            count: g.count || 0,
            filter: { group_id: g.id }
          });
        }
      });
      allGroups.value = system;
      customGroups.value = custom;
      // 系统分组在前、自定义在后（data 本身系统在前，push 顺序天然满足）
      managerGroups.value = manager;
      // 若当前 activeGroup 指向被隐藏的系统分组（count=0 已过滤），回退到「全部」
      if (!system.some(g => g.key === activeGroup.value)) {
        activeGroup.value = "all";
      }
    } catch (e) {
      console.error("获取分组失败：", e);
    }
  }

  /** 便捷切换分组（模板可直接 `activeGroup = key`，此处保留以便语义化调用）。 */
  function setActiveGroup(key: string) {
    activeGroup.value = key;
  }

  function resetActiveGroup() {
    activeGroup.value = "holding";
  }

  return {
    activeGroup,
    allGroups,
    customGroups,
    managerGroups,
    activeGroupLabel,
    currentIsCustom,
    activeCustomGroupId,
    fetchGroups,
    setActiveGroup,
    resetActiveGroup
  };
}
