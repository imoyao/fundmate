/**
 * 对账差异横幅的状态编排（#980 批 B8 从 `DiscrepancyBanner/index.vue` 抽出）。
 *
 * 抽出的理由：这个组件的 `<script setup>` 有 150 行，其中只有「要不要显示」
 * （`routeAllowed`）和「点按钮去哪」与模板有关；剩下的是取数、家庭级 dismiss key、
 * 会话级开关、从工作台返回时的重新拉取——这些都能脱离模板理解与测试。
 *
 * 状态机值得单独说清（三段，任一错都会让横幅「撒谎」）：
 *   1. `loading`（首屏取数中，不显示）→ 2. 已 dismiss（本次会话不再显示）
 *   → 3. `count > 0` 且当前路由该显示（工作台页自己不显示）。
 *
 * ⚠️ `cachedFamilyId` 是**本 composable 调用内**的缓存，不是模块级：本组件挂在布局上、
 * 全局只实例化一次，所以效果等价于页面级；但如果哪天它被用在会反复挂载的地方，
 * 这里就会每次重打一次 /me。
 */
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listDiscrepancies, type DiscrepancyItem } from "@/api/reconciliation";
import { getMe } from "@/api/auth";
import {
  COLLAPSED_LIMIT,
  pendingDays,
  pickDomainBPending,
  shouldShowOnRoute,
  sortByStaleness,
  WORKBENCH_ROUTE_NAME
} from "./helpers";

/** 本次会话是否已关闭的存储前缀（真实 key 见 `dismissKey`） */
const STORAGE_KEY = "recon_pending_banner_dismissed";

export interface UseDiscrepancyBannerOptions {
  /**
   * 是否在挂载时自动跑一次首屏取数（默认 `true`，组件用默认值）。
   *
   * 置 `false` 时首屏改由调用方手动 `refresh()` 驱动。存在的理由：前端单测跑在
   * node 环境（无 DOM、无组件实例），`onMounted` 不会触发，硬测首屏只会在日志里
   * 换出一条「no active component instance」警告，测不到任何东西。
   */
  autoStart?: boolean;
}

export function useDiscrepancyBanner(
  options: UseDiscrepancyBannerOptions = {}
) {
  const route = useRoute();
  const router = useRouter();

  /** 域 B 待处理差异（已按「挂得最久」排序） */
  const pending = ref<DiscrepancyItem[]>([]);
  const loading = ref(true);
  const dismissed = ref(false);
  const expanded = ref(false);

  /**
   * 计算「挂了几天」所依据的基准时刻。
   *
   * 固定在取数那一刻，而不是每次渲染都 `new Date()`：一是模板里反复 new Date
   * 会让同一批数据算出跨天不一致的结果，二是渲染期的隐式时间依赖无法测试。
   */
  const now = ref(new Date());

  /**
   * 按家庭隔离的 dismiss key。
   *
   * 与 `GhostDuplicateBanner` 同口径：单一常量 key 会让换家庭 / 换账号共用同一个开关
   * （语义错误），且「拿不到 family 时退化为无后缀 key」——宁可隔离失效，也不要开关失效。
   */
  function dismissKey(familyId: number | null): string {
    return familyId == null ? STORAGE_KEY : `${STORAGE_KEY}:${familyId}`;
  }

  let cachedFamilyId: number | null | undefined;

  async function resolveFamilyId(): Promise<number | null> {
    if (cachedFamilyId !== undefined) return cachedFamilyId;
    try {
      const res = await getMe();
      cachedFamilyId = res.data?.family?.id ?? null;
    } catch {
      cachedFamilyId = null;
    }
    return cachedFamilyId;
  }

  function isDismissed(familyId: number | null): boolean {
    try {
      return sessionStorage.getItem(dismissKey(familyId)) === "1";
    } catch {
      return false;
    }
  }

  function dismiss(): void {
    dismissed.value = true;
    void resolveFamilyId().then(fid => {
      try {
        sessionStorage.setItem(dismissKey(fid), "1");
      } catch {
        /* ignore */
      }
    });
  }

  /** 拉取域 B 待处理差异并按「挂得最久」排序 */
  async function loadPending(): Promise<void> {
    try {
      const res = await listDiscrepancies({ status: "pending" });
      // 只取域 B（口径说明见 helpers.pickDomainBPending），并按「挂得最久」排序
      now.value = new Date();
      pending.value = sortByStaleness(
        pickDomainBPending(res.data ?? []),
        now.value
      );
    } catch {
      pending.value = [];
    }
  }

  /** 展示条数（域 B 待处理） */
  const count = computed(() => pending.value.length);

  /** 最久未处理的那条已挂多少天（标题里点出来的那一条） */
  const stalestDays = computed(() => {
    if (!pending.value.length) return null;
    return pendingDays(pending.value[0].first_detected_at, now.value);
  });

  /** 收起态最多展示几条 */
  const visibleItems = computed(() =>
    expanded.value ? pending.value : pending.value.slice(0, COLLAPSED_LIMIT)
  );
  const hiddenCount = computed(() =>
    expanded.value ? 0 : Math.max(0, pending.value.length - COLLAPSED_LIMIT)
  );

  /** 当前路由是否该展示（工作台页自带提醒，不重复） */
  const routeAllowed = computed(() => shouldShowOnRoute(route.name as string));

  /** 去对账工作台域 B 处理：横幅上的数字与落地后的「待裁决差异」一致 */
  function goToWorkbench(): void {
    router.push({
      path: "/investment/reconcile-workbench",
      query: { domain: "B" }
    });
  }

  /**
   * 首屏 / 重新进入时的一次完整结算：先定家庭级 dismiss key，关过就直接收摊，
   * 没关过才打接口。
   *
   * 单独成函数而不是塞进 `onMounted` 里：同一条判定要被「挂载」和「从工作台返回」
   * 两处共用，而且脱离生命周期才能被单测直接驱动。
   */
  async function refresh(): Promise<void> {
    const familyId = await resolveFamilyId();
    if (isDismissed(familyId)) {
      loading.value = false;
      return;
    }
    await loadPending();
    loading.value = false;
  }

  if (options.autoStart !== false) onMounted(refresh);

  /**
   * 从工作台返回时重新取数。
   *
   * 为什么需要：本组件挂在**布局**上（布局常驻、路由切换不重挂载），`onMounted`
   * 只在首次进入应用时跑一次。若不刷新，用户在工作台处理完差异再返回其它页面，
   * 横幅仍显示处理前的条数——一个会撒谎的提醒比没有提醒更糟。
   *
   * 只在「上一个路由是工作台」时刷新：其它导航不重复打接口。
   */
  watch(
    () => route.name,
    (next, prev) => {
      if (prev === WORKBENCH_ROUTE_NAME && !dismissed.value) {
        void loadPending();
      }
    }
  );

  return {
    loading,
    dismissed,
    expanded,
    now,
    count,
    stalestDays,
    visibleItems,
    hiddenCount,
    routeAllowed,
    dismiss,
    goToWorkbench,
    refresh
  };
}
