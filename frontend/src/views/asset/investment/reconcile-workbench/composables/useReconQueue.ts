import { computed, ref, type Ref } from "vue";
import type { WorkbenchDomainKey } from "../constants/domainTabs";
import {
  DOMAIN_TO_TASK,
  RECON_QUEUE_STATES,
  RECON_TASKS,
  type ReconQueueState,
  type ReconTaskKey
} from "../constants/reconTasks";
import {
  DEFAULT_QUEUE_FILTER,
  batchableItems,
  buildReconQueue,
  countByState,
  countByTask,
  countOpenItemsByTask,
  filterQueue,
  queueBatchOptions,
  sortQueue,
  type ReconQueueFilter,
  type ReconQueueItem,
  type ReconQueueSource
} from "../utils/reconQueue";

/**
 * 待办队列的**页面状态**（筛选 / 选中 / 计数），与数据加载、写操作分离。
 *
 * - 数据来自 `useWorkbenchDomains` 的只读快照（以 computed 形式传入）；
 * - 所有计数都从同一条 `items` 派生，卡片角标、状态分段器、列表条数不会各数一遍；
 * - 本文件不调用任何写接口。批量动作由 `ReconBatchDialog` 负责。
 */
export function useReconQueue(source: Ref<ReconQueueSource>) {
  const filter = ref<ReconQueueFilter>({ ...DEFAULT_QUEUE_FILTER });
  const selectedIds = ref<string[]>([]);

  const items = computed<ReconQueueItem[]>(() => buildReconQueue(source.value));

  /** 分诊卡角标：还剩下几件待办（不含已处理与入口动作） */
  const taskCounts = computed(() => {
    const result = {} as Record<ReconTaskKey, number>;
    for (const task of RECON_TASKS) {
      result[task.key] = countOpenItemsByTask(items.value, task.key);
    }
    return result;
  });

  /** 任务说明里的「涉及多少条记录」，与角标口径分开写，避免两个数字互相打架 */
  const recordCounts = computed(() => {
    const result = {} as Record<ReconTaskKey, number>;
    for (const task of RECON_TASKS) {
      result[task.key] = countByTask(items.value, task.key);
    }
    return result;
  });

  const readyCounts = computed(() => {
    const result = {} as Record<ReconTaskKey, number>;
    for (const task of RECON_TASKS) {
      result[task.key] = items.value.filter(
        i => i.task === task.key && i.state === "ready" && i.count > 0
      ).length;
    }
    return result;
  });

  /** 横幅与「全部」说明用的总待办项数 */
  const openTotal = computed(() =>
    RECON_TASKS.reduce((sum, task) => sum + taskCounts.value[task.key], 0)
  );

  /** 状态分段器计数随任务筛选联动：先看某一类时，档位只数这一类 */
  const stateCounts = computed(() =>
    countByState(items.value, filter.value.task)
  );

  const stateOptions = computed(() => {
    const scoped = items.value.filter(
      i => filter.value.task === "all" || i.task === filter.value.task
    );
    return [
      { label: "全部", value: "all" as const, count: scoped.length },
      ...RECON_QUEUE_STATES.map(state => ({
        label: state.label,
        value: state.value,
        count: stateCounts.value[state.value]
      }))
    ];
  });

  const visibleItems = computed(() =>
    sortQueue(filterQueue(items.value, filter.value))
  );

  const batchOptions = computed(() => queueBatchOptions(items.value));

  /** 只有「可直接处理」且后端判定可修的项能进批量 */
  const selectableItems = computed(() => batchableItems(visibleItems.value));

  const selectedItems = computed(() =>
    selectableItems.value.filter(i => selectedIds.value.includes(i.id))
  );

  const allSelected = computed(
    () =>
      selectableItems.value.length > 0 &&
      selectedItems.value.length === selectableItems.value.length
  );

  /** 卡片点第二次即取消筛选，不必再造一个「全部」导航项 */
  function selectTask(key: ReconTaskKey): void {
    filter.value.task = filter.value.task === key ? "all" : key;
    pruneSelection();
  }

  function clearTask(): void {
    filter.value.task = "all";
    pruneSelection();
  }

  function setState(state: ReconQueueState | "all"): void {
    filter.value.state = state;
  }

  function setKeyword(keyword: string): void {
    filter.value.keyword = keyword;
  }

  function setBatch(batchId: number | "all"): void {
    filter.value.batchId = batchId;
  }

  function resetFilter(): void {
    filter.value = { ...DEFAULT_QUEUE_FILTER };
    pruneSelection();
  }

  function toggleSelection(id: string): void {
    const index = selectedIds.value.indexOf(id);
    if (index >= 0) selectedIds.value.splice(index, 1);
    else selectedIds.value.push(id);
  }

  function toggleAll(): void {
    selectedIds.value = allSelected.value
      ? []
      : selectableItems.value.map(i => i.id);
  }

  function clearSelection(): void {
    selectedIds.value = [];
  }

  /** 筛选收窄后，已选中但不再可见的项必须取消选中 */
  function pruneSelection(): void {
    const visible = new Set(selectableItems.value.map(i => i.id));
    selectedIds.value = selectedIds.value.filter(id => visible.has(id));
  }

  /**
   * `?domain=A…G` 入站：落到该域所属任务，并把第一条相关待办选中。
   * 域只作寻址与「来源」标签，不重新变成导航维度。
   * 返回选中的队列项 id，供页面层展开处理区。
   */
  function focusDomain(domain: WorkbenchDomainKey): string | null {
    filter.value = {
      ...DEFAULT_QUEUE_FILTER,
      task: DOMAIN_TO_TASK[domain]
    };
    const match = sortQueue(
      items.value.filter(i => i.sourceDomain === domain)
    )[0];
    return match?.id ?? null;
  }

  /** 横幅点击：落到有待办的第一个任务，并展开最靠前的那一条 */
  function focusFirstPending(): string | null {
    const first = RECON_TASKS.find(task => taskCounts.value[task.key] > 0);
    if (!first) return null;
    filter.value = { ...DEFAULT_QUEUE_FILTER, task: first.key };
    return (
      sortQueue(items.value.filter(i => i.task === first.key))[0]?.id ?? null
    );
  }

  return {
    filter,
    items,
    visibleItems,
    taskCounts,
    recordCounts,
    readyCounts,
    openTotal,
    stateCounts,
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
    toggleAll,
    clearSelection,
    focusDomain,
    focusFirstPending
  };
}
