import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { DanglingRefGroup, DiscrepancyItem } from "@/api/reconciliation";
import { normalizeDomain } from "../utils/domainQuery";
import type { WorkbenchDomainKey } from "../constants/domainTabs";
import type { DanglingStage } from "../utils/danglingRefEnrichScope";
import type { ReconDetailContext } from "../utils/reconDetail";
import type { useWorkbenchDomains } from "./useWorkbenchDomains";
import type { useReconQueue } from "./useReconQueue";

/**
 * 页面动作编排：处理区上下文、弹窗状态、入站寻址、批量回补后的刷新。
 *
 * 从 index.vue 拆出，是为了守住 `scripts/check_vue_size.mjs` 的 406 行基线——
 * 页面壳只负责「摆组件 + 传值」，动作与状态各归其位（抽象克制，不引入回调注入）。
 */
export function useWorkbenchActions(
  domains: ReturnType<typeof useWorkbenchDomains>,
  queue: ReturnType<typeof useReconQueue>
) {
  const router = useRouter();
  const route = useRoute();

  /** 元素类型直接从 useReconQueue 的 selectedItems 取（那里 ReconQueueItem 解析正常），
   *  不走本文件直接 import —— 后者的 import.row 字面量在 vue-tsc 下偶发解析成 unknown。 */
  type QueueItem = (typeof queue.selectedItems.value)[number];

  /** 既有域面板继续承载真实写路径与二次确认，这里只做只读快照的组装 */
  const detailContext = computed<ReconDetailContext>(() => ({
    bDiscs: domains.bDiscs.value,
    cDiscs: domains.cDiscs.value,
    loading: domains.loading.value,
    eItems: domains.eItems.value,
    eLoading: domains.eLoading.value,
    eActing: domains.eActing.value,
    ghostGroups: domains.ghostGroups.value,
    ghostIgnored: domains.ghostIgnored.value,
    ghostLoading: domains.ghostLoading.value,
    ghostDeletingId: domains.ghostDeletingId.value,
    ghostUndoingId: domains.ghostUndoingId.value,
    taxItems: domains.taxItems.value,
    taxTotalCents: domains.taxTotalCents.value,
    taxPendingCount: domains.taxPendingCount.value,
    taxDeferredCount: domains.taxDeferredCount.value,
    taxExemptCount: domains.taxExemptCount.value,
    taxLoading: domains.taxLoading.value,
    danglingRefs: domains.danglingRefs.value,
    danglingLoading: domains.danglingLoading.value,
    orphanLedgers: domains.orphanLedgers.value,
    orphanLoading: domains.orphanLoading.value,
    errors: domains.loadErrors.value
  }));

  const activeDetailId = ref<string | null>(null);
  /** 与 item 解耦：入站寻址即使该类一条待办都没有，也要能看到空态处理区 */
  const activeDomain = ref<WorkbenchDomainKey | null>(null);
  /**
   * 域 F 的当前阶段（漏斗，2026-11-13）：阶段聚合项点开的是「阶段面板」，
   * 只列该阶段的组，动作在执行区。非 null 蕴含 activeDomain === "F"。
   */
  const activeStage = ref<DanglingStage | null>(null);
  const activeItem = computed(
    () => queue.items.value.find(i => i.id === activeDetailId.value) ?? null
  );

  const recognizerVisible = ref(false);
  const supplementVisible = ref(false);
  const supplementTarget = ref<DiscrepancyItem | null>(null);
  const danglingFixVisible = ref(false);
  const danglingFixGroup = ref<DanglingRefGroup | null>(null);
  const batchVisible = ref(false);
  const batchBusy = ref(false);
  /** 批量弹窗的数据源：批量勾选或单条孤儿都走 ReconBatchDialog，避免两套入口。
   *  用 computed 暴露，与 useReconQueue 的 selectedItems 同形，vue-tsc 模板解包稳定。 */
  const batchSource = ref<QueueItem[]>([]);
  const batchItems = computed<QueueItem[]>(() => batchSource.value);

  function openSupplement(row: DiscrepancyItem): void {
    supplementTarget.value = row;
    supplementVisible.value = true;
  }

  function openDanglingFix(group: DanglingRefGroup): void {
    danglingFixGroup.value = group;
    danglingFixVisible.value = true;
  }

  function goTo(to: string | { name: string }): void {
    void router.push(to);
  }

  /** 处理区改成右侧抽屉：选中一条只切换抽屉内容，队列不位移、滚动位置不变 */
  const detailOpen = computed(
    () => activeDetailId.value !== null || activeDomain.value !== null
  );

  /** 点队列卡：开抽屉，不切视图、不重挂载、不写 URL，也不滚动页面 */
  function openItem(item: QueueItem): void {
    // 域 F 的阶段聚合项（漏斗，2026-11-13）：点开的是阶段面板，不是单条
    // 执行区——聚合项没有单一载荷，落进单条视图动作只会作用于 groups[0]。
    if (item.payload.kind === "danglingStage") {
      openStage(item.payload.stage);
      return;
    }
    activeDomain.value = item.sourceDomain;
    activeDetailId.value = item.id;
    // 单条聚焦不是阶段面板：换条目时把上一阶段的面板退掉，两个视图不叠加
    activeStage.value = null;
  }

  /**
   * 点域 F 的阶段聚合项（payload.kind === "danglingStage"）：开域 F 的阶段
   * 面板，只列该阶段的组。面板只导航不做写操作（漏斗：动作唯一入口在执行区）。
   */
  function openStage(stage: DanglingStage): void {
    activeDomain.value = "F";
    activeStage.value = stage;
    activeDetailId.value = null;
  }

  /** 翻页后把队列头带回视野，避免用户停在上一段的末尾 */
  function scrollQueueTop(): void {
    scrollTo(".recon-queue");
  }

  function closeDetail(): void {
    activeDomain.value = null;
    activeDetailId.value = null;
    activeStage.value = null;
  }

  function focusBanner(): void {
    const firstId = queue.focusFirstPending();
    const first = firstId
      ? (queue.items.value.find(i => i.id === firstId) ?? null)
      : null;
    // 聚合项不落单条执行区：多组聚合的载荷没有单条 row，硬选会把动作
    // 限成只作用于 groups[0]。与 openItem 的分支保持同一判据。
    if (first?.payload.kind === "danglingStage") {
      openStage(first.payload.stage);
      scrollTo(".recon-queue");
      return;
    }
    activeDetailId.value = firstId;
    activeDomain.value = first?.sourceDomain ?? null;
    activeStage.value = null;
    scrollTo(".recon-queue");
  }

  function openBatch(): void {
    if (queue.selectedItems.value.length === 0) return;
    batchSource.value = queue.selectedItems.value;
    batchVisible.value = true;
  }

  /** 抽屉里单条孤儿「核对并归入账本」：复用同一枚 ReconBatchDialog，只传这一条 */
  function openOrphanFix(item: QueueItem): void {
    batchSource.value = [item];
    batchVisible.value = true;
  }

  async function onBatchSubmitted(): Promise<void> {
    batchBusy.value = true;
    try {
      await Promise.all([domains.reload("dangling"), domains.reload("orphan")]);
      queue.clearSelection();
    } finally {
      batchBusy.value = false;
    }
  }

  function scrollTo(selector: string): void {
    nextTick(() => {
      document
        .querySelector(selector)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  /**
   * `?domain=A…G` 入站寻址：落到对应任务并展开该类处理区（总览面板）。
   * 域只用于寻址与「来源」标签，不重新变成导航维度。
   * 入站只展开「域面板」总览、不自动选中某一条——抽屉 ③ 在选中具体待办时才换成
   * 单条聚焦动作（ReconItemAction），避免 `?domain=` 直达也掉进单条视图、把面板 e2e 覆盖打掉。
   * 首屏数据未回来时 items 为空，故用 pendingDomain 等队列就绪再定位域。
   */
  const pendingDomain = ref<WorkbenchDomainKey | null>(
    normalizeDomain(route.query.domain) ?? null
  );

  watch(
    queue.items,
    () => {
      if (!pendingDomain.value) return;
      const domain = pendingDomain.value;
      activeDomain.value = domain;
      activeStage.value = null;
      queue.focusDomain(domain);
      pendingDomain.value = null;
    },
    { immediate: true }
  );

  watch(
    () => route.query.domain,
    raw => {
      const next = normalizeDomain(raw);
      if (!next) return;
      pendingDomain.value = next;
      activeDomain.value = next;
      activeDetailId.value = null;
      activeStage.value = null;
    }
  );

  /* 切任务 / 切筛选刻意不写回 URL：布局层以 route.fullPath 作 <component :key>，
   * 改写 query 会整页重建并重跑所有加载器（#2706）。`?domain=` 仅作入站寻址。 */
  onMounted(() => {
    void domains.loadAll();
  });

  return {
    detailContext,
    detailOpen,
    activeDetailId,
    activeDomain,
    activeStage,
    activeItem,
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
    openStage,
    closeDetail,
    scrollQueueTop,
    focusBanner,
    openBatch,
    onBatchSubmitted,
    openOrphanFix,
    batchItems
  };
}
