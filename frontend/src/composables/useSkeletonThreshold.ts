// src/composables/useSkeletonThreshold.ts
//
// 骨架屏 200ms 阈值（docs/design/components.md · PageSkeleton 铁律4）的统一实现。
//
// 规则：请求开始后**超过 200ms** 才置 showSkeleton = true；200ms 内返回的快请求
// 全程不渲染骨架屏，避免「骨架刚出现就消失」的闪屏。
//
// 用法（页面仍自己持有 loading；骨架屏渲染条件 = loading && showSkeleton）：
//
//     const { showSkeleton, startSkeleton, settleSkeleton } =
//       useSkeletonThreshold();
//
//     async function load() {
//       loading.value = true;
//       startSkeleton();
//       try {
//         /* ... */
//       } finally {
//         settleSkeleton();
//         loading.value = false;
//       }
//     }
//
// 为什么抽 composable 而不是各页内联：ledgers/detail（useLedgerDetail）、
// useMarketOverview、dividends/index.vue 已有三份同款定时器拷贝，每份都得自己
// 处理「重入时回收孤儿定时器」这个坑（useMarketOverview 的 #1546 T2.5 复查注释
// 讲过：旧句柄残留会在新一轮请求进行中把骨架屏误点亮）。产品详情页（product/detail.vue）
// 已贴近 400 行规模门禁（scripts/check_vue_size.mjs），不宜再塞内联状态机——
// 新代码统一走本 composable；存量内联版不强制回改（逐页迁移另行处理）。
import { ref } from "vue";

export function useSkeletonThreshold(delayMs = 200) {
  const showSkeleton = ref(false);
  let timer: ReturnType<typeof setTimeout> | null = null;

  /** 请求开始时调用：delayMs 后仍未结束才点亮骨架屏 */
  function startSkeleton() {
    // 回收上一轮未触发的定时器——路由切换 / 重试导致请求重入时，
    // 旧句柄会变成孤儿：在新一轮请求进行中就提前点亮骨架屏。
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      showSkeleton.value = true;
    }, delayMs);
  }

  /** 请求结束（成功或失败都算）时调用：清计时器并复位骨架屏 */
  function settleSkeleton() {
    if (timer) clearTimeout(timer);
    timer = null;
    showSkeleton.value = false;
  }

  return { showSkeleton, startSkeleton, settleSkeleton };
}
