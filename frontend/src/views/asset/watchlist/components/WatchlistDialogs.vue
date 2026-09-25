<script setup lang="ts">
import { computed, type Ref } from "vue";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import OcrImportModal from "@/components/QuickEntry/OcrImportModal.vue";
import SettingsDrawer from "@/components/Watchlist/SettingsDrawer.vue";
import TagManagerDialog from "@/components/Watchlist/TagManagerDialog.vue";
import GroupManagerDialog from "@/components/Watchlist/GroupManagerDialog.vue";
// #987：组内产品增删（与 GroupManagerDialog 管「分组本身」分工不同）
import GroupItemsDialog from "@/components/Watchlist/GroupItemsDialog.vue";
// #1449 多分组管理：行操作列「加入分组」弹层（一个产品可属多个自定义分组）
import GroupMultiSelectDialog from "@/components/Watchlist/GroupMultiSelectDialog.vue";
import TagEditorDialog from "@/components/Watchlist/TagEditorDialog.vue";
import NotesEditorDialog from "@/components/Watchlist/NotesEditorDialog.vue";
import WatchlistRemoveDialog from "@/views/asset/watchlist/components/WatchlistRemoveDialog.vue";
import WatchlistQuickViewDrawer from "@/views/asset/watchlist/components/WatchlistQuickViewDrawer.vue";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { useWatchlistData } from "@/composables/useWatchlistData";
import type { useWatchlistToolbar } from "@/composables/useWatchlistToolbar";
import type { useWatchlistValuation } from "@/views/asset/watchlist/composables/useWatchlistValuation";
import type { useWatchlistPageActions } from "@/views/asset/watchlist/composables/useWatchlistPageActions";
import type { WatchlistColumnVisibility } from "@/composables/useWatchlistColumnVisibility";

/**
 * 自选页弹窗集合（#980 P0-b 拆分自 index.vue，零行为变更）：
 * 添加 / OCR 导入 / 移除 / 标签管理 / 分组管理 / 组内产品（#987）/ 多分组（#1449）/
 * 行内标签与备注编辑 / 行速览抽屉（#1285）/ 管理设置抽屉。
 * 弹窗位置不变（页面根节点下、非 CardBlock 内），teleport 行为与拆分前一致。
 */
const props = defineProps<{
  toolbar: ReturnType<typeof useWatchlistToolbar>;
  data: ReturnType<typeof useWatchlistData>;
  groups: ReturnType<typeof useWatchlistGroups>;
  tags: ReturnType<typeof useWatchlistTags>;
  valuation: ReturnType<typeof useWatchlistValuation>;
  actions: ReturnType<typeof useWatchlistPageActions>;
  columnSettings: WatchlistColumnVisibility;
}>();

/** 实例内部 ref → v-model 桥接（状态注入模式） */
function bridge<T>(source: Ref<T>) {
  return computed({
    get: () => source.value,
    set: (value: T) => {
      source.value = value;
    }
  });
}

const addDialogVisible = bridge(props.toolbar.addDialogVisible);
const ocrDialogVisible = bridge(props.toolbar.ocrDialogVisible);
const groupManagerVisible = bridge(props.toolbar.groupManagerVisible);
const tagManagerVisible = bridge(props.toolbar.tagManagerVisible);
const settingsDrawerVisible = bridge(props.toolbar.settingsDrawerVisible);
const removeDialogVisible = bridge(props.data.removeDialogVisible);
const removeScope = bridge(props.data.removeScope);
const showTagEditor = bridge(props.data.showTagEditor);
const showNotesEditor = bridge(props.data.showNotesEditor);
const groupItemsVisible = bridge(props.actions.groupItemsVisible);
const multiGroupVisible = bridge(props.actions.multiGroupVisible);
const quickViewVisible = bridge(props.actions.quickViewVisible);
</script>

<template>
  <!-- 弹窗部分 -->
  <AddToWatchlistModal
    v-model="addDialogVisible"
    :initial-group-id="groups.activeCustomGroupId.value"
    @submitted="actions.onItemAdded"
    @catalog-changed="actions.onCatalogChanged"
  />

  <OcrImportModal
    v-model="ocrDialogVisible"
    @imported="actions.onOcrImported"
  />

  <!-- 移除自选弹窗（已抽取为 WatchlistRemoveDialog 组件） -->
  <WatchlistRemoveDialog
    v-model="removeDialogVisible"
    v-model:remove-scope="removeScope"
    :removing-item="data.removingItem.value"
    :current-is-custom="groups.currentIsCustom.value"
    @confirm="data.executeRemove"
  />

  <!-- 标签管理弹窗（共有组件 TagManagerDialog，自本页拆出，见 docs/design/components.md） -->
  <TagManagerDialog
    v-model="tagManagerVisible"
    :all-tags="tags.allTags.value"
    :tag-usage="actions.tagUsage.value"
    @tags-changed="tags.fetchTags"
  />

  <!-- 分组管理弹窗（GitHub Labels 风格，与标签同构，见 docs/design/components.md）。
       系统分组可见但不可编辑/删除（managerGroups 含系统分组虚拟行），自定义分组可管理。 -->
  <GroupManagerDialog
    v-model="groupManagerVisible"
    :all-groups="groups.managerGroups.value"
    @groups-changed="groups.fetchGroups"
  />

  <!-- 分组内产品增删弹窗（#987）：管理「某个自定义分组里有哪些产品」，
       与上方 GroupManagerDialog（管理分组本身）分工互补。系统分组不提供该能力
       （activeCustomGroup 为 null 时弹窗不展示内容）。 -->
  <GroupItemsDialog
    v-model="groupItemsVisible"
    :group="actions.activeCustomGroup.value"
    @changed="actions.onGroupItemsChanged"
  />

  <!-- #1449 多分组管理：行操作列「加入分组」弹层（一个产品可属多个自定义分组） -->
  <GroupMultiSelectDialog
    v-model="multiGroupVisible"
    :item="actions.multiGroupItem.value"
    :groups="groups.customGroups.value"
    @changed="actions.onMultiGroupChanged"
  />

  <!-- 行内标签编辑弹窗（共有组件 TagEditorDialog） -->
  <TagEditorDialog
    v-model="showTagEditor"
    :item="data.editingItem.value"
    :all-tags="tags.allTags.value"
    @saved="actions.onTagEditorSaved"
  />

  <!-- 行内备注编辑弹窗（#1285） -->
  <NotesEditorDialog
    v-model="showNotesEditor"
    :item="data.editingNotesItem.value"
    @saved="actions.onNotesSaved"
  />

  <!-- 行「速览」抽屉（#1285）：行点击打开，备注可一键进入编辑 -->
  <WatchlistQuickViewDrawer
    v-model="quickViewVisible"
    :item="actions.quickViewItem.value"
    :all-tags="tags.allTags.value"
    @edit-notes="data.openNotesEditor"
  />

  <SettingsDrawer
    v-model="settingsDrawerVisible"
    :realtime-enabled="valuation.realtimeEnabled.value"
    :refresh-interval="valuation.realtime.refreshInterval.value"
    :column-settings="columnSettings"
    @refresh-interval-change="valuation.realtime.setRefreshInterval"
    @manage-groups="
      groupManagerVisible = true;
      settingsDrawerVisible = false;
    "
    @manage-tags="
      tagManagerVisible = true;
      settingsDrawerVisible = false;
    "
    @manage-batch="
      toolbar.toggleBatchMode();
      settingsDrawerVisible = false;
    "
  />
</template>
