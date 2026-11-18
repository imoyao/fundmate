/**
 * 页内导航的「滚动几何」原语（#2922，从 `usePageNav` 剥离）。
 *
 * ## 为什么单独一层
 *
 * `usePageNav` 实际是两件事拼在一起的：
 * 1. **导航状态机**——锚点扫描、scroll-spy、跳转意图（pin）、rAF 收敛，这些是
 *    有状态的、与「这次调用」绑定的（`usePageNav` 的闭包）；
 * 2. **滚动几何测量**——「谁在滚」「定位线在哪」「还能滚多远」，全部是无状态的
 *    DOM 度量，输入是应用布局（fixedHeader 与否），与「哪个页面在用」无关。
 *
 * 原先两者混在 540 行里，读代码时得来回确认「这个常量影响的是动画还是度量」。
 * 几何层剥离后，`usePageNav` 只剩状态机，本文件的函数可单独推理 / 单测（纯读 DOM）。
 *
 * ## 缓存口径（原样保留，勿"优化"）
 *
 * `cachedScroller` 模块级共享是**安全**的：滚动容器只由布局决定，与调用方无关。
 * 但 **null 不缓存**：容器 watch 里 scan() 刚设完 items 时 nav 的重渲染还没发生，
 * 那一刻查询会扑空；把 null 缓存下来会让定位线永远按「无滚动容器」算（实测
 * scroll-spy 整体少算一个页头高度，active 停在前一个区块）。
 * 失效点只有两处：视口变化（布局模式 / 侧边栏折叠可能换宿主）与卸载。
 */

/** 滚动宿主抽象：fixedHeader 模式是 `.el-scrollbar__wrap`，非 fixed 模式
 *  整页滚动（window）。read/write/limit 三件套让动画循环不关心当前是哪种布局。 */
export interface ScrollHost {
  read: () => number;
  write: (top: number) => void;
  limit: () => number;
}

let cachedScroller: HTMLElement | null | undefined;

/** 找最近的可滚动祖先：fixedHeader 模式下是 `.el-scrollbar__wrap`，
 *  非 fixed 模式整页滚动（window）。判据用「真能滚」而不是单看 overflow——
 *  `.app-main` 也是 overflow:hidden，但它不滚（scrollHeight == clientHeight）。 */
export function findScroller(el: HTMLElement): HTMLElement | null {
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

/** 吸顶后的滚动容器（fixedHeader 模式下是 `.el-scrollbar__wrap`，非 fixed 模式
 *  整页滚动返回 null）。缓存 + resize 失效：滚动容器不随滚动变，但随视口变
 *  （布局模式 / 侧边栏折叠都可能切换滚动宿主）。**null 不缓存**，见文件头。 */
export function currentScroller(): HTMLElement | null {
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
export function spyLine(): number {
  const nav = document.querySelector<HTMLElement>(".page-nav");
  const base = currentScroller()?.getBoundingClientRect().top ?? 0;
  return base + (nav?.offsetHeight ?? 0) + 8;
}

export function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function clamp(v: number, min: number, max: number): number {
  return Math.min(Math.max(v, min), max);
}

/** 解析滚动宿主（goTo 用，从目标区块往上找）。返回 null = 没有可滚内容
 *  （页面比视口矮），跳转无从谈起——置了 active 即可。 */
export function scrollHostFor(el: HTMLElement): ScrollHost | null {
  const scroller = findScroller(el);
  if (scroller && scroller.scrollHeight > scroller.clientHeight + 1) {
    return {
      read: () => scroller.scrollTop,
      write: top => {
        scroller.scrollTop = top;
      },
      limit: () => scroller.scrollHeight - scroller.clientHeight
    };
  }
  const limit = document.documentElement.scrollHeight - window.innerHeight;
  if (limit > 1) {
    return {
      read: () => window.scrollY,
      write: top => window.scrollTo(0, top),
      limit: () => document.documentElement.scrollHeight - window.innerHeight
    };
  }
  return null;
}

/** 滚动度量（scroll-spy 的触底判据用）。与 scrollHostFor 同源，但走
 *  cachedScroller 缓存路径——scroll 事件每帧都可能调，不值得再走一遍
 *  findScroller。返回 null = 无可滚内容。 */
export function scrollMetrics(): { top: number; limit: number } | null {
  const scroller = currentScroller();
  if (scroller) {
    return {
      top: scroller.scrollTop,
      limit: scroller.scrollHeight - scroller.clientHeight
    };
  }
  const limit = document.documentElement.scrollHeight - window.innerHeight;
  if (limit > 1) {
    return { top: window.scrollY, limit };
  }
  return null;
}

/** 作废滚动容器缓存：视口变化（布局模式 / 侧边栏折叠）与卸载时调用。 */
export function resetScrollerCache(): void {
  cachedScroller = undefined;
}
