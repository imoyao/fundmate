import { ref } from "vue";
import type { WatchlistItem } from "@/api/watchlist";

/**
 * 自选列表顶部工具栏（搜索 / 批量模式 / 视图 segmented / 弹窗开关）状态收口（2026-08-20）。
 *
 * 设计边界：
 * - 搜索关键字、批量模式、视图 segmented 仅本 composable 持有，供 useWatchlistData 拼 fetchParams 消费。
 * - 弹窗（添加自选 / OCR 导入 / 分组管理 / 标签管理 / 设置抽屉）的可见性也在此统一管辖，
 *   页面模板只负责把开关绑定到对应组件——保持「状态在 composable、视图在组件」的单一职责。
 */
export function useWatchlistToolbar() {
  // 顶部搜索框
  const searchKeyword = ref("");
  // 视图 segmented：全部 / 场内 / 场外（唯一 venue 入口，方案 B 收敛三套）
  const currentView = ref<"all" | "exchange" | "otc">("all");
  // 资产类型多选筛选（「类型」弹层，2026-09-09 用户拍板方案 A）：
  // 与 venue 维度正交，可组合使用（如「场内 + 股票/ETF」）。
  // 存 asset_type 小写枚举，空数组 = 不过滤
  const selectedAssetTypes = ref<string[]>([]);
  // 批量选择模式
  const batchMode = ref(false);
  const selectedItems = ref<WatchlistItem[]>([]);
  // 批量移动目标分组（下拉草稿）
  const batchMoveGroupId = ref<number | null>(null);

  // 弹窗开关（页面模板绑定到对应组件）
  const addDialogVisible = ref(false);
  const ocrDialogVisible = ref(false);
  const groupManagerVisible = ref(false);
  const tagManagerVisible = ref(false);
  const settingsDrawerVisible = ref(false);

  /** 退出批量模式时清空已选项 */
  function toggleBatchMode() {
    batchMode.value = !batchMode.value;
    if (!batchMode.value) selectedItems.value = [];
  }

  function openAddDialog() {
    addDialogVisible.value = true;
  }
  function openOcrDialog() {
    ocrDialogVisible.value = true;
  }
  function openGroupManager() {
    groupManagerVisible.value = true;
  }
  function openTagManager() {
    tagManagerVisible.value = true;
  }
  function openSettingsDrawer() {
    settingsDrawerVisible.value = true;
  }

  return {
    searchKeyword,
    currentView,
    selectedAssetTypes,
    batchMode,
    selectedItems,
    batchMoveGroupId,
    addDialogVisible,
    ocrDialogVisible,
    groupManagerVisible,
    tagManagerVisible,
    settingsDrawerVisible,
    toggleBatchMode,
    openAddDialog,
    openOcrDialog,
    openGroupManager,
    openTagManager,
    openSettingsDrawer
  };
}
