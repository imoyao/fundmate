import {
  nextTick,
  onActivated,
  onBeforeUnmount,
  onMounted,
  ref,
  watch
} from "vue";
import type { Ref } from "vue";
import type { ProductResolveResult } from "@/api/products";

/**
 * 详情页页内导航的状态与 scroll-spy（#1968 子卡：顶部锚点胶囊 + xl 右目录 rail）。
 *
 * ## 形态（调研结论：docs/working-notes/product-detail-research-2026-10-12.md §5.3）
 * - `< xl`：内容区顶部锚点胶囊（sticky 在页头下，横向可滑不换行）；
 * - `>= xl`：右侧目录 rail（sticky，~160px）。
 * 两级都由 `ProductPageNav` / `ProductPageToc` 两个展示组件渲染，state 收口在本文件。
 *
 * ## 为什么不在 detail.vue 里写
 * 该文件已 378 行，再塞 scroll-spy 会越过 `scripts/check_vue_size.mjs` 的 400 行线；
 * 且 spy 逻辑（监听 / 观察 / 定位）与「区块怎么挂载」是两层关注点。
 *
 * ## 锚点从哪来：DOM 存在性过滤，而不是静态清单
 * 区块是否渲染由各组件自己决定（走势对 manager 整卡不渲染、持仓明细无披露数据时
 * 不渲染、第三方数据无链接时不渲染……）。静态清单必然长出死链——点一下原地不动。
 * 故导航项 = 扫描容器里真实存在的 `nav-` 锚点，按 DOM 序出列表；
 * 异步到位的区块（持仓明细要等一次请求）由 MutationObserver 补扫。
 * 代价：新增区块若忘了挂锚点，导航里就没有它——用 DEV 告警兜底（见 scan）。
 */

export interface PageNavItem {
  /** 区块锚点 id（挂在 CardBlock 根上，见 detail.vue 的 attribute fallthrough） */
  id: string;
  label: string;
}

/** 锚点 id → 导航标签。与各区块的 SectionHeader 标题保持一致（读屏与视觉同一套词汇）。 */
const NAV_LABELS: Record<string, string> = {
  "nav-position": "我的持仓",
  "nav-trend": "走势",
  "nav-transactions": "交易记录",
  "nav-fund": "基金资料",
  "nav-performance": "业绩与风险",
  // 「行业配置 + 持仓明细」共用一个容器端点（#2029 卡 C），合并为一个入口
  "nav-holdings": "行业与持仓",
  "nav-index": "指数资料",
  "nav-manager": "基金经理",
  "nav-advisor": "投顾组合",
  "nav-bond": "深度分析",
  "nav-related": "关联标的",
  "nav-external": "第三方数据"
};

const ANCHOR_PREFIX = "nav-";

/** 股票 / ETF 的区块标题是动态的（`ProductStockSection.sectionTitle`），导航标签随之 */
function labelFor(
  id: string,
  assetType: string | undefined
): string | undefined {
  if (id === "nav-stock") {
    return assetType === "etf" ? "ETF 行情" : "股票行情";
  }
  return NAV_LABELS[id];
}

/** 吸顶后的滚动容器（fixedHeader 模式下是 `.el-scrollbar__wrap`，非 fixed 模式
 *  整页滚动返回 null）。缓存 + resize 失效：滚动容器不随滚动变，但随视口变
 *  （布局模式 / 侧边栏折叠都可能切换滚动宿主）。
 *  **null 不缓存**：容器 watch 里 scan() 刚设完 items，nav 的重渲染还没发生，
 *  那一刻查询会扑空；若把 null 缓存下来，定位线会永远按「无滚动容器」算
 *  （实测 scroll-spy 整体少算一个页头高度，active 停在前一个区块）。 */
let cachedScroller: HTMLElement | null | undefined;

function currentScroller(): HTMLElement | null {
  if (cachedScroller) return cachedScroller;
  const nav = document.querySelector<HTMLElement>(".page-nav");
  const found = nav ? findScroller(nav) : null;
  if (found) cachedScroller = found;
  return found;
}

/** 吸顶定位线（视口坐标）：滚动容器顶沿 + 胶囊高 + 8px 呼吸位。
 *  **不能取胶囊当前 rect**：页面在顶部时胶囊尚未吸顶、rect 偏下，点击跳转会
 *  少滚一截（实测差约 130px，落点悬在胶囊下方）。取容器顶沿即吸顶后的位置。
 *  xl+ 胶囊 display:none（offsetHeight 0），线退到容器顶沿 + 8。 */
function spyLine(): number {
  const nav = document.querySelector<HTMLElement>(".page-nav");
  const base = currentScroller()?.getBoundingClientRect().top ?? 0;
  return base + (nav?.offsetHeight ?? 0) + 8;
}

/** 找最近的可滚动祖先：fixedHeader 模式下是 `.el-scrollbar__wrap`，
 *  非 fixed 模式整页滚动（window）。判据用「真能滚」而不是单看 overflow——
 *  `.app-main` 也是 overflow:hidden，但它不滚（scrollHeight == clientHeight）。 */
function findScroller(el: HTMLElement): HTMLElement | null {
  let node: HTMLElement | null = el.parentElement;
  while (node) {
    const overflowY = getComputedStyle(node).overflowY;
    const scrollable = node.scrollHeight > node.clientHeight + 1;
    if (
      scrollable &&
      (overflowY === "auto" || overflowY === "scroll" || overflowY === "hidden")
    ) {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function useProductPageNav(
  product: Ref<ProductResolveResult | null>,
  /** 区块容器（detail.vue 的 `.product-detail__main`）：MutationObserver 挂它身上，
   *  不监听 document.body——全应用的 DOM 变更都会变成无谓的重扫。 */
  container: Ref<HTMLElement | undefined>
) {
  const items = ref<PageNavItem[]>([]);
  const activeId = ref("");

  /** 重扫导航项：容器里真实存在的锚点，按 DOM 序，未登记的跳过并 DEV 告警 */
  function scan() {
    const root = container.value;
    if (!root) return;
    const assetType = product.value?.asset_type;
    const next: PageNavItem[] = [];
    root
      .querySelectorAll<HTMLElement>(`[id^="${ANCHOR_PREFIX}"]`)
      .forEach(el => {
        const label = labelFor(el.id, assetType);
        if (!label) {
          if (import.meta.env.DEV) {
            console.warn(
              `[page-nav] 未登记标签的锚点：${el.id}（请在 NAV_LABELS 补上）`
            );
          }
          return;
        }
        next.push({ id: el.id, label });
      });
    items.value = next;
  }

  /** scroll-spy：最后一个越过定位线的区块为当前项；都在线下方时取第一项 */
  function updateActive() {
    const line = spyLine();
    let current = "";
    for (const item of items.value) {
      const el = document.getElementById(item.id);
      if (!el) continue;
      if (el.getBoundingClientRect().top <= line) current = item.id;
    }
    activeId.value = current || items.value[0]?.id || "";
  }

  /** 点击跳转：把目标区块顶边送到定位线处。先置 active 给即时反馈，
   *  滚动途中的 scroll 事件会按实际位置继续纠正（标准 scroll-spy 行为）。 */
  function goTo(id: string) {
    const el = document.getElementById(id);
    if (!el) return;
    activeId.value = id;
    const delta = el.getBoundingClientRect().top - spyLine();
    const behavior: ScrollBehavior = prefersReducedMotion() ? "auto" : "smooth";
    const scroller = findScroller(el);
    if (scroller) {
      scroller.scrollTo({ top: scroller.scrollTop + delta, behavior });
    } else {
      window.scrollTo({ top: window.scrollY + delta, behavior });
    }
  }

  // 滚动监听挂在 document 捕获段：scroll 不冒泡，但捕获段能收到**任何**元素
  // 的滚动事件——不必关心当前布局下真正滚动的是 el-scrollbar 还是 window。
  let rafId = 0;
  function onScroll() {
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      updateActive();
    });
  }

  function onResize() {
    // 视口宽度变化可能切换滚动宿主 / 侧边栏折叠，定位线随之变
    cachedScroller = undefined;
    onScroll();
  }

  let observer: MutationObserver | null = null;

  /**
   * 容器是 `v-else-if="product"` 分支里才渲染的：路由挂载时（本 composable 的
   * onMounted 跑完的时点）`product` 还是 null，容器还不存在。**必须等 ref 被
   * 赋值再建 observer**——在 onMounted 里建会整个扑空（实测：经理页走势卡卸载后
   * 「走势」胶囊死赖着不走；基金页持仓明细异步到位后胶囊迟迟不上菜单）。
   */
  watch(
    container,
    root => {
      observer?.disconnect();
      observer = null;
      if (!root) return;
      // 异步到位的区块（走势等 kind、持仓明细等一次请求）挂载 / 卸载后补扫，不留死链
      observer = new MutationObserver(() => {
        scan();
        updateActive();
      });
      observer.observe(root, { childList: true, subtree: true });
      scan();
      updateActive();
    },
    { immediate: true }
  );

  onMounted(() => {
    document.addEventListener("scroll", onScroll, {
      capture: true,
      passive: true
    });
    window.addEventListener("resize", onResize);
  });

  onActivated(() => {
    // keep-alive 恢复时滚动位置可能已被浏览器还原，active 需重算
    scan();
    updateActive();
  });

  onBeforeUnmount(() => {
    document.removeEventListener("scroll", onScroll, { capture: true });
    window.removeEventListener("resize", onResize);
    observer?.disconnect();
    if (rafId) cancelAnimationFrame(rafId);
    cachedScroller = undefined;
  });

  // 品类切换（基金 → 股票等）：等 patch 完再扫，否则读到的是上一页的 DOM
  watch(product, () => nextTick(scan));

  return { items, activeId, goTo };
}
