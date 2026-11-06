/**
 * 自选列表「行内操作 + 批量操作」（#2931，D88）。
 *
 * ## 为什么这里**没有** `fetchData`
 *
 * 本文件里的每个写操作只做三件事：调后端、提示、**返回「数据已变更」信号**。
 * 列表怎么重新拉取（拉整页？拉全量？回到第几页？沿用当前筛选？）一律由
 * 父层 `useWatchlistData` 决定——它是唯一持有 `fetchParams` 与 `allItems` 的地方。
 *
 * 拆出来之前这些函数各自在结尾直接调 `fetchData()`，看似简单，但那是「刷新出口
 * 分散在 5 个操作里」：一旦某个操作既自己刷新、又被父级的 watch 兜底刷新一次，
 * 就是两次请求。而且这种重复**不会报错**——只是白拉一遍全量（`fields=lite`
 * 最多 4 页），表现成「点一下有点卡」。把「要不要刷新」变成返回值（而不是副作用），
 * 调用方就无法在不知情的情况下多刷一次：子域没有 `fetchData` 可调。
 *
 * ## 约定
 *
 * - 每个 `Promise<boolean>`：`true` = 后端数据已变更，**父级应重新拉列表**；
 *   `false` = 未写库（虚拟行跳过 / 被防呆闸门拦下 / 请求失败 / 用户取消），
 *   这些情况刷新没有意义，还会把用户看到的提示与刚被清空的选择状态搅在一起。
 * - 批量模式退出、选择清空、弹窗关闭属于「操作本身的收尾」，留在这里；
 *   它们不触发任何 watch，因此不会引发第二次请求。
 */
import type { Ref } from "vue";
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  updateWatchlistItem,
  deleteWatchlistItem,
  removeItemFromGroup,
  addItemToGroup,
  type WatchlistItem
} from "@/api/watchlist";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";

/** 行内 / 批量操作需要的分组上下文（只取两个派生态，不拖整个 groups 进来） */
export interface RowActionGroupContext {
  /** 当前激活的自定义分组 id（「仅从当前分组移除」用）；非自定义分组时为 undefined */
  activeCustomGroupId: ReturnType<
    typeof useWatchlistGroups
  >["activeCustomGroupId"];
  /** 当前是否为自定义分组（决定移除弹窗的默认范围） */
  currentIsCustom: ReturnType<typeof useWatchlistGroups>["currentIsCustom"];
}

/** 批量操作依赖的工具栏状态（`WatchlistToolbarState` 的子集，结构兼容可直接传） */
export interface RowActionToolbarContext {
  batchMode: Ref<boolean>;
  selectedItems: Ref<WatchlistItem[]>;
  batchMoveGroupId: Ref<number | undefined>;
}

export function useWatchlistRowActions(
  groupCtx: RowActionGroupContext,
  toolbar: RowActionToolbarContext
) {
  const { activeCustomGroupId, currentIsCustom } = groupCtx;
  const { batchMode, selectedItems, batchMoveGroupId } = toolbar;

  // ─────────────────────────────────────────────
  // 行内操作（置顶 / 特别关注 / 移除）
  // ─────────────────────────────────────────────

  /** 置顶 / 取消置顶。虚拟持仓行（id=null）无自选记录，跳过。
   * @returns 是否已写库（true ⇒ 父级需重新拉列表） */
  async function togglePin(row: WatchlistItem): Promise<boolean> {
    if (row.id == null) return false;
    try {
      await updateWatchlistItem(row.id, { is_pinned: !row.is_pinned });
      ElMessage.success(row.is_pinned ? "已取消置顶" : "已置顶");
      return true;
    } catch (e) {
      ElMessage.error("置顶操作失败");
      console.error("置顶错误：", e);
      return false;
    }
  }

  /** 特别关注 / 取消特别关注。虚拟持仓行同样跳过。
   * @returns 是否已写库 */
  async function toggleFavorite(row: WatchlistItem): Promise<boolean> {
    if (row.id == null) return false;
    try {
      await updateWatchlistItem(row.id, { favorite: !row.favorite });
      ElMessage.success(row.favorite ? "已取消特别关注" : "已设为特别关注");
      return true;
    } catch (e) {
      ElMessage.error("关注操作失败");
      console.error("关注错误：", e);
      return false;
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

  /** 执行移除：从当前分组移除（仅自定义分组）或彻底删除自选。
   * @returns 是否已写库（持仓资产被闸门拦下、请求失败时均为 false） */
  async function executeRemove(): Promise<boolean> {
    const item = removingItem.value;
    if (!item || item.id == null) return false;
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
          return false;
        }
        await deleteWatchlistItem(item.id);
        ElMessage.success("已移除自选");
      }
      removeDialogVisible.value = false;
      return true;
    } catch (e) {
      ElMessage.error("移除操作失败");
      console.error("移除错误：", e);
      return false;
    }
  }

  // ─────────────────────────────────────────────
  // 批量操作
  // ─────────────────────────────────────────────

  function handleSelectionChange(selection: WatchlistItem[]) {
    selectedItems.value = selection;
  }

  /** 批量移除。
   * @returns 是否已写库（全被闸门拦下 / 用户取消时 false） */
  async function batchDelete(): Promise<boolean> {
    if (selectedItems.value.length === 0) return false;
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
      return false;
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
      return true;
    } catch {
      /* 用户取消 */
      return false;
    }
  }

  /** 批量移动到分组。
   * @returns 是否已写库（无目标分组 / 无选中项 / 请求失败时 false） */
  async function batchMoveToGroup(
    groupId: number | null | undefined
  ): Promise<boolean> {
    if (!groupId || selectedItems.value.length === 0) return false;
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
      return true;
    } catch {
      ElMessage.error("批量移动失败");
      return false;
    }
  }

  return {
    togglePin,
    toggleFavorite,
    confirmRemove,
    executeRemove,
    removingItem,
    removeScope,
    removeDialogVisible,
    handleSelectionChange,
    batchDelete,
    batchMoveToGroup
  };
}
