<template>
  <div class="recon-workbench-page">
    <WorkbenchHead
      :running="running"
      :updated-at="updatedAt"
      @run="handleRun"
    />

    <!-- 内容列与 PageHeaderBar 同宽同内边距，保证左边缘严格对齐（design.md 页头规范） -->
    <div class="recon-shell">
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

      <!-- ① 主行动引导：能一键处理 → 一键 CTA；否则引导去判断；全空给清空态 -->
      <ReconActionHero
        :ready-count="readyCount"
        :judge-count="judgeCount"
        :loading="isLoading"
        @batch="openBatchAll"
        @go-judge="setSegment('judge')"
        @go-import="goTo('/inventory/investment/import')"
      />

      <!-- 待入库草稿：折叠成一行，展开包两个候选面板 -->
      <ReconDraftSummary
        :candidates="recognizerCandidates"
        :committing="committing"
        @discard="discardCandidates"
        @commit="commitCandidates"
      />

      <ShareIntegrityPanel
        v-if="shareItems.length > 0"
        :items="shareItems"
        @go-transactions="goShareTransactions"
        @clear="clearShareByBill"
      />

      <!-- ② 状态分段 + ③ 列表 -->
      <section class="recon-queue">
        <SectionHeader
          :title="taskLabel ? `待办队列 · ${taskLabel}` : '待办队列'"
        />

        <ReconQueueFilter
          :segment="filter.segment"
          :options="segmentOptions"
          :keyword="filter.keyword"
          :batch-id="filter.batchId"
          :batch-options="batchOptions"
          :result-count="visibleItems.length"
          @update:segment="setSegment"
          @update:keyword="setKeyword"
          @update:batch-id="setBatch"
          @reset="resetFilter"
        />

        <!-- judge 段内类型 chips：把要你判断再按三类财务动作细分 -->
        <ReconTaskChips
          v-if="filter.segment === 'judge'"
          :active="filter.task"
          :counts="chipCounts"
          @select="selectTask"
        />

        <ReconTaskBrief v-if="filter.task !== 'all'" :task="filter.task" />

        <ReconStatusState
          :loading="isLoading"
          :empty="visibleItems.length === 0"
          empty-title="这个筛选下没有待办"
          empty-hint="换一个分段或清除关键词，也可以点分段器查看已处理记录。"
        >
          <ul class="recon-queue__list">
            <ReconQueueCard
              v-for="item in pagedItems"
              :key="item.id"
              :item="item"
              :active="activeDetailId === item.id"
              @open="openItem"
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
        @recompute="handleRecompute"
        @ignore="handleIgnore"
        @fix-dangling="openDanglingFix"
        @eaccount-cover="handleEAccountCover"
        @eaccount-ignore="handleEAccountIgnore"
        @ghost-ignore="handleGhostIgnore"
        @ghost-undo-ignore="handleGhostUndoIgnore"
        @ghost-delete-txn="handleGhostDeleteTxn"
        @go-to="goTo"
        @fix-orphan="openOrphanFix"
        @recognize="recognizerVisible = true"
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
import type { ShareIntegrityItem } from "@/api/reconciliation";
import SoftBanner from "@/components/SoftBanner/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import RecognizerImportModal from "@/components/QuickEntry/RecognizerImportModal.vue";
import WorkbenchHead from "./components/WorkbenchHead.vue";
import ReconActionHero from "./components/ReconActionHero.vue";
import ReconDraftSummary from "./components/ReconDraftSummary.vue";
import ReconTaskBrief from "./components/ReconTaskBrief.vue";
import ReconTaskChips from "./components/ReconTaskChips.vue";
import ReconQueueFilter from "./components/ReconQueueFilter.vue";
import ReconStatusState from "./components/ReconStatusState.vue";
import ReconQueueCard from "./components/ReconQueueCard.vue";
import ReconQueuePagination from "./components/ReconQueuePagination.vue";
import ReconQueueDetail from "./components/ReconQueueDetail.vue";
import ReconBatchDialog from "./components/ReconBatchDialog.vue";
import SupplementDialog from "./components/SupplementDialog.vue";
import DanglingRefFixDialog from "./components/DanglingRefFixDialog.vue";
import ShareIntegrityPanel from "./components/ShareIntegrityPanel.vue";
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
  shareItems,
  clearShareByBill,
  recognizerCandidates,
  committing,
  dataDateLabel,
  loadErrors,
  reload,
  loadAll,
  handleRun,
  handleIgnore,
  handleRecompute,
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

/** 首屏加载态：数据未回时 ready=0 是假象，必须压住自动落档 */
const isLoading = computed(
  () =>
    domains.loading.value ||
    domains.eLoading.value ||
    domains.ghostLoading.value ||
    domains.taxLoading.value ||
    domains.danglingLoading.value ||
    domains.orphanLoading.value
);

const queue = useReconQueue(queueSource, isLoading);
const {
  filter,
  visibleItems,
  page,
  pageSize,
  pagedItems,
  setPage,
  setPageSize,
  segmentOptions,
  chipCounts,
  readyCount,
  judgeCount,
  batchOptions,
  selectTask,
  setSegment,
  setKeyword,
  setBatch,
  resetFilter
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
  openSupplement,
  openDanglingFix,
  goTo,
  openItem,
  closeDetail,
  scrollQueueTop,
  openBatchAll,
  onBatchSubmitted,
  openOrphanFix,
  batchItems
} = useWorkbenchActions(domains, queue);

/** 「去核对补录流水」：交易流水页支持 `?symbol=` 预置筛选（TransactionList 的既有能力） */
function goShareTransactions(item: ShareIntegrityItem): void {
  goTo(`/transactions?symbol=${encodeURIComponent(item.symbol)}`);
}

const taskLabel = computed(() => {
  const task = filter.value.task;
  return task === "all" ? null : taskMeta(task).label;
});
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
