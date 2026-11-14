<template>
  <div class="recon-workbench-page">
    <WorkbenchHead
      :running="running"
      :updated-at="updatedAt"
      @recognize="recognizerVisible = true"
      @run="handleRun"
    />

    <!-- 内容列与 PageHeaderBar 同宽同内边距，保证左边缘严格对齐（design.md 页头规范） -->
    <div class="recon-shell">
      <WorkbenchBanner
        v-if="openTotal > 0"
        :total="openTotal"
        @go="focusBanner"
      />

      <!-- 部分 loader 失败不能伪装成「没有待办」：明确报出来并给重试入口 -->
      <SoftBanner
        v-if="errorCount > 0"
        class="recon-load-error"
        variant="warning"
        icon="ep:warning"
      >
        有 {{ errorCount }} 类数据没能加载，待办队列可能不完整。
        <template #actions>
          <el-button size="small" @click="loadAll">重新加载</el-button>
        </template>
      </SoftBanner>

      <ReconStatBar
        :open-items="openTotal"
        :ready-items="readyTotal"
        :open-records="openRecords"
      />

      <WorkbenchTaskCards
        :active="filter.task"
        :counts="taskCounts"
        @select="selectTask"
      />

      <!-- 「全部待办」不给说明条：待办总数、可直接处理数、三张任务卡已经在上面说清了 -->
      <ReconTaskBrief
        v-if="filter.task !== 'all'"
        :task="filter.task"
        :count="activeRecordCount"
        @clear="clearTask"
        @go-import="goTo('/inventory/investment/import')"
      />

      <!-- 识别草稿是「要确认入库的事」，不是域 tab；两类草稿各自只在有内容时渲染 -->
      <RecognizerCandidatesPanel
        kind="holding"
        :candidates="recognizerCandidates"
        :committing="committing"
        @discard="discardCandidates"
        @commit="commitCandidates"
      />
      <RecognizerCandidatesPanel
        kind="txn"
        :candidates="recognizerCandidates"
        :committing="committing"
        @discard="discardCandidates"
        @commit="commitCandidates"
      />

      <section class="recon-queue">
        <SectionHeader
          :title="taskLabel ? `待办队列 · ${taskLabel}` : '待办队列'"
        />

        <ReconQueueFilter
          :state="filter.state"
          :options="stateOptions"
          :keyword="filter.keyword"
          :batch-id="filter.batchId"
          :batch-options="batchOptions"
          :result-count="visibleItems.length"
          :selectable-count="selectableItems.length"
          :selected-count="selectedItems.length"
          :selected-records="selectedRecords"
          :all-selected="allSelected"
          :busy="batchBusy"
          @update:state="setState"
          @update:keyword="setKeyword"
          @update:batch-id="setBatch"
          @toggle-all="toggleAll"
          @batch="openBatch"
          @reset="resetFilter"
        />

        <ReconStatusState
          :loading="isLoading"
          :empty="visibleItems.length === 0"
          empty-title="这个筛选下没有待办"
          empty-hint="换一个状态或清除关键词，也可以点上方任务卡查看其它类别。"
        >
          <ul class="recon-queue__list">
            <ReconQueueCard
              v-for="item in pagedItems"
              :key="item.id"
              :item="item"
              :active="activeDetailId === item.id"
              :selectable="selectableIds.has(item.id)"
              :selected="selectedIds.includes(item.id)"
              @open="openItem"
              @toggle="toggleSelection"
            />
          </ul>
        </ReconStatusState>

        <ReconQueuePagination
          :page="page"
          :page-size="pageSize"
          :total="visibleItems.length"
          @update:page="setPage"
          @update:page-size="setPageSize"
          @changed="scrollQueueTop"
        />
      </section>

      <ReconQueueDetail
        :item="activeItem"
        :open="detailOpen"
        :domain="activeDomain"
        :ctx="detailContext"
        :active-stage="activeStage"
        @close="closeDetail"
        @refresh="reload"
        @supplement="openSupplement"
        @ignore="handleIgnore"
        @fix-dangling="openDanglingFix"
        @eaccount-cover="handleEAccountCover"
        @eaccount-ignore="handleEAccountIgnore"
        @ghost-ignore="handleGhostIgnore"
        @ghost-undo-ignore="handleGhostUndoIgnore"
        @ghost-delete-txn="handleGhostDeleteTxn"
        @go-to="goTo"
        @fix-orphan="openOrphanFix"
      />

      <SupplementDialog
        v-model="supplementVisible"
        :target="supplementTarget"
        @submitted="reload('discrepancies')"
      />
      <DanglingRefFixDialog
        v-model="danglingFixVisible"
        :group="danglingFixGroup"
        @submitted="reload('dangling')"
      />
      <RecognizerImportModal
        v-model="recognizerVisible"
        @saved="reload('candidates')"
      />
      <ReconBatchDialog
        v-model="batchVisible"
        :items="batchItems"
        @submitted="onBatchSubmitted"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { usePageRefresh } from "@/composables/usePageRefresh";
import SoftBanner from "@/components/SoftBanner/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import RecognizerImportModal from "@/components/QuickEntry/RecognizerImportModal.vue";
import WorkbenchHead from "./components/WorkbenchHead.vue";
import WorkbenchBanner from "./components/WorkbenchBanner.vue";
import ReconStatBar from "./components/ReconStatBar.vue";
import WorkbenchTaskCards from "./components/WorkbenchTaskCards.vue";
import ReconTaskBrief from "./components/ReconTaskBrief.vue";
import RecognizerCandidatesPanel from "./components/RecognizerCandidatesPanel.vue";
import ReconQueueFilter from "./components/ReconQueueFilter.vue";
import ReconStatusState from "./components/ReconStatusState.vue";
import ReconQueueCard from "./components/ReconQueueCard.vue";
import ReconQueuePagination from "./components/ReconQueuePagination.vue";
import ReconQueueDetail from "./components/ReconQueueDetail.vue";
import ReconBatchDialog from "./components/ReconBatchDialog.vue";
import SupplementDialog from "./components/SupplementDialog.vue";
import DanglingRefFixDialog from "./components/DanglingRefFixDialog.vue";
import { taskMeta } from "./constants/reconTasks";
import type { ReconQueueSource } from "./utils/reconQueue";
import { useWorkbenchDomains } from "./composables/useWorkbenchDomains";
import { useReconQueue } from "./composables/useReconQueue";
import { useWorkbenchActions } from "./composables/useWorkbenchActions";

defineOptions({ name: "ReconcileWorkbench" });

/** 七个 loader 与写操作收口在 useWorkbenchDomains；队列状态收口在 useReconQueue；
 *  弹窗与寻址收口在 useWorkbenchActions。本文件只负责「摆组件 + 传值」。 */
const domains = useWorkbenchDomains();
const {
  running,
  discs,
  eItems,
  ghostGroups,
  ghostIgnored,
  taxItems,
  danglingRefs,
  orphanLedgers,
  recognizerCandidates,
  committing,
  dataDateLabel,
  loadErrors,
  reload,
  loadAll,
  handleRun,
  handleIgnore,
  handleEAccountCover,
  handleEAccountIgnore,
  handleGhostIgnore,
  handleGhostUndoIgnore,
  handleGhostDeleteTxn,
  commitCandidates,
  discardCandidates
} = domains;

/** 任何写操作（本页或其它页）之后全量重拉七个域：旧实现只刷命中的那一域，
 *  其余域的计数与队列仍是上一轮快照，用户会以为操作没生效。防抖 300ms 会自动合并。 */
usePageRefresh(() => void loadAll());

/** 七个后端域的原始快照 → 一条用户待办队列（纯函数，见 utils/reconQueue.ts） */
const queueSource = computed<ReconQueueSource>(() => ({
  discrepancies: discs.value,
  eItems: eItems.value,
  ghostGroups: ghostGroups.value,
  ghostIgnored: ghostIgnored.value,
  taxItems: taxItems.value,
  dangling: danglingRefs.value,
  orphan: orphanLedgers.value
}));

const queue = useReconQueue(queueSource);
const {
  filter,
  visibleItems,
  page,
  pageSize,
  pagedItems,
  setPage,
  setPageSize,
  taskCounts,
  recordCounts,
  readyCounts,
  openTotal,
  stateOptions,
  batchOptions,
  selectableItems,
  selectedIds,
  selectedItems,
  allSelected,
  selectTask,
  clearTask,
  setState,
  setKeyword,
  setBatch,
  resetFilter,
  toggleSelection,
  toggleAll
} = queue;

const {
  detailContext,
  detailOpen,
  activeDetailId,
  activeDomain,
  activeItem,
  activeStage,
  recognizerVisible,
  supplementVisible,
  supplementTarget,
  danglingFixVisible,
  danglingFixGroup,
  batchVisible,
  batchBusy,
  openSupplement,
  openDanglingFix,
  goTo,
  openItem,
  closeDetail,
  scrollQueueTop,
  focusBanner,
  openBatch,
  onBatchSubmitted,
  openOrphanFix,
  batchItems
} = useWorkbenchActions(domains, queue);

const selectableIds = computed(
  () => new Set(selectableItems.value.map(i => i.id))
);
const readyTotal = computed(() =>
  Object.values(readyCounts.value).reduce((sum, n) => sum + n, 0)
);
const openRecords = computed(() =>
  Object.values(recordCounts.value).reduce((sum, n) => sum + n, 0)
);
const activeRecordCount = computed(() =>
  filter.value.task === "all"
    ? openRecords.value
    : recordCounts.value[filter.value.task]
);
const taskLabel = computed(() =>
  filter.value.task === "all" ? null : taskMeta(filter.value.task).label
);
const selectedRecords = computed(() =>
  selectedItems.value.reduce((sum, i) => sum + i.count, 0)
);
const isLoading = computed(
  () =>
    domains.loading.value ||
    domains.eLoading.value ||
    domains.ghostLoading.value ||
    domains.taxLoading.value ||
    domains.danglingLoading.value ||
    domains.orphanLoading.value
);
const errorCount = computed(() => Object.keys(loadErrors.value).length);
const updatedAt = computed(() =>
  dataDateLabel.value === "—" ? "" : `${dataDateLabel.value} 数据`
);
</script>

<style scoped>
.recon-workbench-page {
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}

.recon-shell {
  display: flex;
  flex-direction: column;
  max-width: var(--layout-content-width);
  padding: 0 var(--space-standard);
  margin: 0 auto;
}

.recon-queue {
  margin-top: var(--space-standard);
}

.recon-queue__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 0;
  margin: 0;
}
</style>
