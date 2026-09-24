// src/composables/market/useMarketOverview.ts
// 探市·大类资产观察 数据 composable：供 ExploreAssetOverview 使用。
import { ref } from "vue";
import { getMarketOverview, type MarketOverviewResponse } from "@/api/market";

export function useMarketOverview() {
  /** 请求进行中 */
  const loading = ref(false);
  /** 错误（网络/后端异常），不阻断页面其余部分 */
  const error = ref<string | null>(null);
  /** 完整响应 data */
  const overview = ref<MarketOverviewResponse["data"] | null>(null);
  // 骨架屏阈值控制：请求 ≤200ms 返回时直接渲染内容、跳过骨架屏，避免“闪屏”（见 #1546 T2.3）
  const showSkeleton = ref(false);
  let skeletonTimer: ReturnType<typeof setTimeout> | null = null;

  const fetchOverview = async (force = false) => {
    loading.value = true;
    error.value = null;
    // 200ms 后才显示骨架屏：快速请求（<200ms）不显示，避免骨架刚出现就消失的闪屏
    skeletonTimer = setTimeout(() => {
      showSkeleton.value = true;
    }, 200);
    try {
      const res = await getMarketOverview(force);
      const data = res.data;
      if (!data) throw new Error("无效响应");
      overview.value = data;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      error.value = msg || "加载失败";
    } finally {
      if (skeletonTimer) {
        clearTimeout(skeletonTimer);
        skeletonTimer = null;
      }
      showSkeleton.value = false;
      loading.value = false;
    }
  };

  return {
    loading,
    error,
    overview,
    fetchOverview,
    showSkeleton
  };
}
