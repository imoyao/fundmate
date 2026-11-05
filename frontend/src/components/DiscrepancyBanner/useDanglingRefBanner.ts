/**
 * 悬空引用站外提醒（#2866）：与 DiscrepancyBanner 的域 B 提醒并列，但**独立取数**。
 *
 * 为什么不塞进 `useDiscrepancyBanner.refresh()`：那条链以 `await` 收口，把新接口挂进去，
 * 新接口一旦超时就会让域 B 横幅的 `loading` 永远收不掉（整条提醒消失）。两个提醒的
 * 数据源与文案互不依赖，各自 onMounted 取数、各自 catch 降级，是唯一不会互相拖垮的接法。
 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listDanglingRefs } from "@/api/reconciliation";
import { shouldShowOnRoute } from "./helpers";

export function useDanglingRefBanner() {
  const route = useRoute();
  const router = useRouter();
  const count = ref(0);
  const loading = ref(true);

  async function refresh(): Promise<void> {
    try {
      const res = await listDanglingRefs();
      count.value = res.data?.total ?? 0;
    } catch {
      count.value = 0;
    } finally {
      loading.value = false;
    }
  }
  onMounted(refresh);

  /** 工作台页自带域 F 视图与角标，站外提醒不重复（复用同一纯函数口径） */
  const routeAllowed = computed(() => shouldShowOnRoute(route.name as string));

  /** 直达域 F：?domain=F 由 normalizeDomain 落地，不再回落到 B */
  function goToDangling(): void {
    router.push({
      path: "/investment/reconcile-workbench",
      query: { domain: "F" }
    });
  }

  return { count, loading, routeAllowed, goToDangling, refresh };
}
