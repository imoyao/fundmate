import { provide } from "vue";
import {
  LAZY_SECTION_REGISTRY,
  type LazySectionRegistry
} from "@/components/LazySection/registry";

/**
 * 把 `usePageNav` 的 `goTo` 包一层：**目标区块还没挂载时，先挂载再跳**。
 *
 * ## 为什么需要这层
 *
 * `LazySection` 让锚点常驻、内容懒挂。好处是导航项永远完整（DOM 扫描仍是唯一
 * 真相源），代价是「点一个还没滚到的区块」时目标内容还不在 DOM 里——跳过去只有
 * 一块空白，内容要等 IntersectionObserver 回调才长出来，用户看到的就是「跳了个
 * 寂寞，然后页面自己往下拱」。
 *
 * 故跳转前先按 anchorId 激活目标（`LazySection` 挂载时把自己注册进
 * `LAZY_SECTION_REGISTRY`，见 components/LazySection/registry.ts）。
 *
 * ## 为什么激活后同步跳，不 `await nextTick()`
 *
 * `goTo` 只把目标区块的**顶边**送到定位线，而顶边位置只由上方内容决定——激活
 * 目标自身不改变它的顶边。`goTo` 内部逐帧重读 rect 的动画循环会自然吸收「该块
 * 内容进 DOM 后页面变长」这件事（`host.limit()` 每帧重算）。
 *
 * 前提是**占位高度接近真实高度**（见 LazySection 的 min-height 约定）：若占位矮
 * 到整页比视口还短，`goTo` 会因「没有可滚内容」提前返回，跳转就落空了。
 *
 * ## 用法（页面 setup 顶层，会 provide）
 *
 * ```ts
 * const nav = usePageNav(pageMain, { labels: NAV_LABELS });
 * const goToNavSection = useLazyNav(nav);
 * ```
 */
export function createLazyNav(
  nav: { goTo: (id: string) => void },
  registry: LazySectionRegistry
): (id: string) => void {
  return (id: string) => {
    // 顺序是契约：先激活（内容进 DOM），再跳。反过来会跳到占位块上。
    registry.get(id)?.();
    nav.goTo(id);
  };
}

export function useLazyNav(nav: { goTo: (id: string) => void }) {
  const registry: LazySectionRegistry = new Map();
  provide(LAZY_SECTION_REGISTRY, registry);
  return createLazyNav(nav, registry);
}
