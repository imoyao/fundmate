import { computed, ref, watch, type Ref } from "vue";
import type { WorkbenchDomainKey } from "../constants/domainTabs";
import {
  DOMAIN_TO_TASK,
  RECON_QUEUE_SEGMENTS,
  RECON_TASKS,
  type ReconQueueSegment,
  type ReconTaskKey
} from "../constants/reconTasks";
import {
  DEFAULT_QUEUE_FILTER,
  batchableItems,
  buildReconQueue,
  countBySegment,
  countJudgeItemsByTask,
  filterQueue,
  queueBatchOptions,
  sortQueue,
  type ReconQueueFilter,
  type ReconQueueItem,
  type ReconQueueSource
} from "../utils/reconQueue";

/**
 * 待办队列的**页面状态**（筛选 / 计数 / 分页），与数据加载、写操作分离。
 *
 * - 数据来自 `useWorkbenchDomains` 的只读快照（以 computed 形式传入）；
 * - 所有计数都从同一条 `items` 派生，分段器、chips、主行动引导不会各数一遍；
 * - 本文件不调用任何写接口。一键处理动作由 `ReconBatchDialog` 负责；
 * - `isLoading` 用于抑制「首屏数据未回、ready 误判为 0 → 落 judge」的假空档。
 */
export function useReconQueue(
  source: Ref<ReconQueueSource>,
  isLoading: Ref<boolean>
) {
  const filter = ref<ReconQueueFilter>({ ...DEFAULT_QUEUE_FILTER });

  const items = computed<ReconQueueItem[]>(() => buildReconQueue(source.value));

  /** 分段器计数随任务筛选联动：先看某一类时，档位只数这一类 */
  const segmentCounts = computed(() =>
    countBySegment(items.value, filter.value.task)
  );

  /** judge 段内类型 chips 计数：按三类任务归集，入口动作不计数 */
  const chipCounts = computed(() => {
    const result = {} as Record<ReconTaskKey, number>;
    for (const task of RECON_TASKS) {
      result[task.key] = countJudgeItemsByTask(items.value, task.key);
    }
    return result;
  });

  /** 全量 ready 项（一键处理的范围，判据单一来源 batchableItems） */
  const allReadyItems = computed(() => batchableItems(items.value));
  const readyCount = computed(() => allReadyItems.value.length);
  const judgeCount = computed(() => countBySegment(items.value, "all").judge);

  const segmentOptions = computed(() =>
    RECON_QUEUE_SEGMENTS.map(seg => ({
      label: seg.label,
      value: seg.value,
      count: segmentCounts.value[seg.value]
    }))
  );

  const visibleItems = computed(() =>
    sortQueue(filterQueue(items.value, filter.value))
  );

  /** 客户端分页：几百条待办不能全堆一页（owner 第二轮）。
   *  visibleItems 仍是全量，计数以它为准，分页只管渲染。 */
  const page = ref(1);
  const pageSize = ref(10);
  const pageCount = computed(() =>
    Math.max(1, Math.ceil(visibleItems.value.length / pageSize.value))
  );
  const pagedItems = computed(() => {
    const start = (page.value - 1) * pageSize.value;
    return visibleItems.value.slice(start, start + pageSize.value);
  });

  /** 换任务 / 换分段 / 搜索都回到第一页 */
  watch(
    filter,
    () => {
      page.value = 1;
    },
    { deep: true }
  );
  /** 处理完一条后当前页可能整页消失，退回最后一页而不是留一片空白 */
  watch(visibleItems, () => {
    if (page.value > pageCount.value) page.value = pageCount.value;
  });

  /**
   * 默认展示「能一键处理(ready)」，ready=0 时自动落到「要你判断(judge)」。
   * 首屏数据未回（isLoading）不落档，否则空队列会被误判成「没有 ready」而跳档。
   */
  watch(
    [() => filter.value.segment, readyCount, judgeCount, isLoading],
    ([segment, ready, judge, loading]) => {
      if (loading) return;
      if (segment === "ready" && ready === 0 && judge > 0) {
        filter.value.segment = "judge";
      }
    },
    { immediate: true }
  );

  function setPage(value: number): void {
    page.value = Math.max(1, Math.min(value, pageCount.value));
  }

  function setPageSize(value: number): void {
    pageSize.value = value;
    page.value = 1;
  }

  const batchOptions = computed(() => queueBatchOptions(items.value));

  /** 卡片点第二次即取消筛选，不必再造一个「全部」导航项 */
  function selectTask(key: ReconTaskKey): void {
    filter.value.task = filter.value.task === key ? "all" : key;
  }

  function clearTask(): void {
    filter.value.task = "all";
  }

  function setSegment(segment: ReconQueueSegment): void {
    filter.value.segment = segment;
  }

  function setKeyword(keyword: string): void {
    filter.value.keyword = keyword;
  }

  function setBatch(batchId: number | "all"): void {
    filter.value.batchId = batchId;
  }

  function resetFilter(): void {
    filter.value = { ...DEFAULT_QUEUE_FILTER };
  }

  /**
   * `?domain=A…G` 入站：落到该域所属任务。域 F 的阶段聚合项已全折入 repair，
   * 不再需要「F 不设任务筛选」的特判（旧 rebuild 拆任务时才有跨任务问题）。
   * 返回选中的队列项 id，供页面层展开处理区。
   */
  function focusDomain(domain: WorkbenchDomainKey): string | null {
    filter.value =
      domain === "F"
        ? { ...DEFAULT_QUEUE_FILTER }
        : { ...DEFAULT_QUEUE_FILTER, task: DOMAIN_TO_TASK[domain] };
    const match = sortQueue(
      items.value.filter(i => i.sourceDomain === domain)
    )[0];
    return match?.id ?? null;
  }

  return {
    filter,
    items,
    visibleItems,
    page,
    pageSize,
    pageCount,
    pagedItems,
    setPage,
    setPageSize,
    segmentCounts,
    segmentOptions,
    chipCounts,
    allReadyItems,
    readyCount,
    judgeCount,
    batchOptions,
    selectTask,
    clearTask,
    setSegment,
    setKeyword,
    setBatch,
    resetFilter,
    focusDomain
  };
}
