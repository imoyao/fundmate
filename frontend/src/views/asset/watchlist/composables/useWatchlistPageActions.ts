import { ref, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  getHoldingGaps,
  reconcileWatchlist,
  type HoldingGap,
  type WatchlistItem,
  type WatchlistGroup
} from "@/api/watchlist";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { useWatchlistData } from "@/composables/useWatchlistData";
import type { useWatchlistToolbar } from "@/composables/useWatchlistToolbar";

interface PageActionsOptions {
  groups: ReturnType<typeof useWatchlistGroups>;
  tags: ReturnType<typeof useWatchlistTags>;
  toolbar: ReturnType<typeof useWatchlistToolbar>;
  data: ReturnType<typeof useWatchlistData>;
}

/**
 * 自选页页面动作域（#980 P0-b 拆分自 index.vue，零行为变更）：
 * 持仓缺口提示与一键补齐（#1458 后续）、自定义分组「组内产品增删」（#987）、
 * 多分组管理入口（#1449）、行「速览」抽屉、标签使用统计，以及各弹窗的
 * 「保存后刷新」回调编排。
 */
export function useWatchlistPageActions(options: PageActionsOptions) {
  const { groups, tags, toolbar, data } = options;
  const { currentIsCustom, activeCustomGroupId, customGroups, fetchGroups } =
    groups;
  const { selectedFilterTagIds, fetchTags } = tags;
  const { searchKeyword, addDialogVisible, ocrDialogVisible } = toolbar;
  const { items, fetchData } = data;

  // ── #987：自定义分组「组内产品增删」──
  // 与「管理分组」（GroupManagerDialog，管理分组本身的新建/改名/删除）分工不同：
  // 本弹窗只管「某个自定义分组里有哪些产品」，对应空白组快捷添加 + 常规组内增删。
  // 系统分组由后端规律方法维护，不提供组内增删（activeCustomGroup 为 null 即不生效）。
  const groupItemsVisible = ref(false);

  // ── #1458 后续：持仓即自选 —— 缺口提示与一键补齐 ──
  const holdingGaps = ref<HoldingGap[]>([]);
  const reconciling = ref(false);

  async function fetchHoldingGaps(): Promise<void> {
    try {
      const res = await getHoldingGaps();
      holdingGaps.value = res.data ?? [];
    } catch {
      // 缺口检测失败不影响主列表，静默
      holdingGaps.value = [];
    }
  }

  async function handleAddAllToWatchlist(): Promise<void> {
    reconciling.value = true;
    try {
      await reconcileWatchlist(true);
      ElMessage.success("已为持仓补齐自选，现在可打标签 / 写备注");
      await fetchHoldingGaps();
      await fetchData();
    } catch {
      ElMessage.error("一键加入自选失败，请稍后重试");
    } finally {
      reconciling.value = false;
    }
  }

  /** 当前选中的自定义分组对象；系统分组或未选中时为 null */
  const activeCustomGroup = computed<WatchlistGroup | null>(() => {
    const gid = activeCustomGroupId.value;
    if (gid == null) return null;
    return customGroups.value.find(g => g.id === gid) ?? null;
  });

  // 从自定义分组切到系统分组时，自动关闭「本组产品」抽屉，
  // 避免 activeCustomGroup 变为 null 后左栏显示「本组产品 0 项」的困惑。
  watch(currentIsCustom, isCustom => {
    if (!isCustom && groupItemsVisible.value) {
      groupItemsVisible.value = false;
    }
  });

  /** 空态是否落在「空白自定义分组」：需为自定义分组且未叠加标签筛选
      （叠加了标签筛选时的空结果是筛选无匹配，不应引导去加产品） */
  const isEmptyCustomGroup = computed(
    () =>
      currentIsCustom.value &&
      selectedFilterTagIds.value.length === 0 &&
      !searchKeyword.value
  );

  function openGroupItemsDialog(): void {
    // 防呆：系统分组（含「全部」）由后端规律维护，不支持手动增删成员。
    // 「管理本组产品」按钮虽已用 v-if=currentIsCustom 拦截，此处再兜底，
    // 防止任何入口（空态快捷入口等）在系统分组下误开弹窗。
    if (!currentIsCustom.value) {
      ElMessage.warning("系统分组（含「全部」）由系统维护，不能手动增删成员");
      return;
    }
    groupItemsVisible.value = true;
  }

  function onManageGroupItems(): void {
    if (!currentIsCustom.value) {
      ElMessage.warning("系统分组（含「全部」）由系统维护，不能手动增删成员");
      return;
    }
    groupItemsVisible.value = true;
  }

  // ── #1449 多分组管理：行操作列「加入分组」入口 ──
  const multiGroupVisible = ref(false);
  const multiGroupItem = ref<WatchlistItem | null>(null);
  function openMultiGroupDialog(row: WatchlistItem): void {
    multiGroupItem.value = row;
    multiGroupVisible.value = true;
  }
  /** 多分组增删成功后：分组计数与列表都需刷新（与 onGroupItemsChanged 同源） */
  function onMultiGroupChanged(): void {
    fetchGroups();
    fetchData();
  }

  /** 组内增删成功后：分组计数与列表都需刷新（#987 验收标准：计数与列表实时生效） */
  function onGroupItemsChanged(): void {
    void fetchGroups();
    void fetchData();
  }

  // 标签使用统计：供 TagManagerDialog 显示每个标签被多少自选使用
  const tagUsage = computed(() => {
    const usage = new Map<number, number>();
    if (!Array.isArray(items.value)) return usage;
    items.value.forEach(item => {
      const tagIds = item?.tag_ids;
      if (Array.isArray(tagIds)) {
        tagIds.forEach(id => {
          if (typeof id === "number" && !isNaN(id)) {
            usage.set(id, (usage.get(id) || 0) + 1);
          }
        });
      }
    });
    return usage;
  });

  function onItemAdded() {
    addDialogVisible.value = false;
    fetchData();
    fetchTags();
  }

  // 弹窗内新建/编辑了标签或分组，立即刷新页面目录，避免页面不更新的问题
  function onCatalogChanged() {
    groups.fetchGroups();
    tags.fetchTags();
  }

  function onOcrImported() {
    ocrDialogVisible.value = false;
    fetchData();
    fetchTags();
  }

  /** 标签保存成功（含弹窗内新建标签）后：刷新列表与标签 */
  const onTagEditorSaved = () => {
    fetchData();
    fetchTags();
  };

  /** 备注保存成功后：刷新列表（单元格即时反映最新笔记） */
  const onNotesSaved = () => {
    fetchData();
  };

  // ── 行「速览」抽屉（#1285）──
  // 设计：行点击 → 抽屉（速览）→ 抽屉内「查看详情」→ 详情页。
  // 行内按钮（标签/备注/操作）已各自 stopPropagation，不触发速览；此处再对
  // .el-button 兜底过滤，避免操作列按钮点击时误开抽屉。
  const quickViewVisible = ref(false);
  const quickViewItem = ref<WatchlistItem | null>(null);

  function onRowClick(
    row: WatchlistItem,
    _column: unknown,
    event: Event
  ): void {
    const el = event.target as HTMLElement | null;
    if (el?.closest(".el-button, button, .add-tag-btn, .add-note-btn")) return;
    quickViewItem.value = row;
    quickViewVisible.value = true;
  }

  return {
    groupItemsVisible,
    holdingGaps,
    reconciling,
    fetchHoldingGaps,
    handleAddAllToWatchlist,
    activeCustomGroup,
    isEmptyCustomGroup,
    openGroupItemsDialog,
    onManageGroupItems,
    multiGroupVisible,
    multiGroupItem,
    openMultiGroupDialog,
    onMultiGroupChanged,
    onGroupItemsChanged,
    tagUsage,
    onItemAdded,
    onCatalogChanged,
    onOcrImported,
    onTagEditorSaved,
    onNotesSaved,
    quickViewVisible,
    quickViewItem,
    onRowClick
  };
}
