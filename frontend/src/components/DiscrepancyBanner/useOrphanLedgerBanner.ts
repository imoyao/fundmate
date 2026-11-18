/**
 * 缺账本孤儿流水站外提醒（#2875）：与域 B / 域 F 的横幅并列，**独立取数**。
 *
 * 与 ``useDanglingRefBanner`` 同构、刻意不复用一条链：三个提醒的数据源与文案互不
 * 依赖，任一接口超时都不该让另外两个横幅的 ``loading`` 收不掉（整条提醒消失）。
 * 各自 onMounted、各自 catch 降级是唯一不会互相拖垮的接法。
 *
 * 计数口径取 ``total``（含 blocked），不是 ``fixable_count``：横幅回答的是
 * 「有多少条流水不进任何账户视图」，把无法归属的那部分藏在数字之外等于少报。
 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listOrphanLedgers } from "@/api/reconciliation";
import { shouldShowOnRoute } from "./helpers";

export function useOrphanLedgerBanner() {
  const route = useRoute();
  const router = useRouter();
  const count = ref(0);
  const loading = ref(true);

  async function refresh(): Promise<void> {
    try {
      const res = await listOrphanLedgers();
      count.value = res.data?.total ?? 0;
    } catch {
      count.value = 0;
    } finally {
      loading.value = false;
    }
  }
  onMounted(refresh);

  /** 工作台页自带域 G 视图与角标，站外提醒不重复（复用同一纯函数口径） */
  const routeAllowed = computed(() => shouldShowOnRoute(route.name as string));

  /** 直达域 G：?domain=G 由 normalizeDomain 落地，不再回落到 B */
  function goToOrphanLedger(): void {
    router.push({
      path: "/investment/reconcile-workbench",
      query: { domain: "G" }
    });
  }

  return { count, loading, routeAllowed, goToOrphanLedger, refresh };
}
