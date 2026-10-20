import {
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
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
 * 不渲染、更多数据无链接时不渲染……）。静态清单必然长出死链——点一下原地不动。
 * 故导航项 = 扫描容器里真实存在的 `nav-` 锚点，按 DOM 序出列表；
 * 异步到位的区块（持仓明细要等一次请求）由 MutationObserver 补扫。
 * 代价：新增区块若忘了挂锚点，导航里就没有它——用 DEV 告警兜底（见 scan）。
 *
 * ## 滚动架构：单一滚动权威（2026-10-14 修「胶囊来回弹跳」后定型）
 * 用户实测症状：点胶囊页面确实跳了，但高亮「概率性跳对、偶尔来回弹」。
 * 探针复现出三个缺陷，修复后架构收敛为——
 * - **scroll-spy 只读**：updateActive 按实测位置算当前项；
 * - **goTo 的 rAF 循环只写**：动画期间 updateActive 整体让位（anim 闸门），
 *   高亮 pin 在点击目标上，两者不互相拉扯；
 * - **每帧重读目标 rect**：布局突变（走势卡数据到位、从「正在读取」长成
 *   300px 图表，下方区块整体下移）时自适应。原生 `scrollTo({behavior:
 *   'smooth'})` 的终点只算一次，必然过期（实测过冲 800+px）；
 * - **定位线判据带 4px 容差**：落点正好把区块顶边压在线上（实测残差
 *   ±0.5px），零容差会被平滑滚动末速的亚像素抖动翻转符号；
 * - **末段吸附 + 看门狗按实际位移续期**：Chromium 取整小数 scrollTop，
 *   距 maxScroll 2px 时每帧 0.4px 的推进被吃光，几何逼近永不收敛（实测
 *   rAF 空转 7s+）。故进入 4px 吸附带直接写目标值；看门狗以写后读回的
 *   实际位移为准续期，真实停摆才强制收尾；
 * - **pin 活到用户接管为止**：停稳后高亮不「终算一次」——maxScroll 截断
 *   下点倒数第二项会滚到底，此时触底兜底会把高亮改写成最后一项（实测：
 *   点「关联标的」高亮跑「更多数据」）。故 goTo 的意图（pinnedId）在
 *   用户自行滚动 / 布局变化前持续有效，触底兜底只作用于无 pin 的
 *   自然滚动；
 * - **触底时当前项 = 最后一项**（仅无 pin 时）：maxScroll 截断下最后一项
 *   永远到不了定位线（实测差 400-600px），老判据会把高亮永久停在倒数第二项。
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
  "nav-external": "更多数据",
  "nav-pro": "高级洞察 Pro"
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

/** 滚动宿主抽象：fixedHeader 模式是 `.el-scrollbar__wrap`，非 fixed 模式
 *  整页滚动（window）。read/write/limit 三件套让 goTo 的动画循环不关心
 *  当前是哪种布局（视口宽度 / 侧边栏折叠都可能切换宿主）。 */
interface ScrollHost {
  read: () => number;
  write: (top: number) => void;
  limit: () => number;
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(Math.max(v, min), max);
}

/** 解析滚动宿主（goTo 用，从目标区块往上找）。返回 null = 没有可滚内容
 *  （页面比视口矮），跳转无从谈起——置了 active 即可。 */
function scrollHostFor(el: HTMLElement): ScrollHost | null {
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

/** 滚动度量（updateActive 的触底判据用）。与 scrollHostFor 同源，但走
 *  cachedScroller 缓存路径——scroll 事件每帧都可能调，不值得再走一遍
 *  findScroller。返回 null = 无可滚内容。 */
function scrollMetrics(): { top: number; limit: number } | null {
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

/** 定位线容差（px）：goTo 的落点会把区块顶边正好压在定位线上（实测残差
 *  ±0.5px）。零容差判据下残差为正（区块低 0.1px）就不算越过、高亮退回
 *  前一项——平滑滚动末速的亚像素抖动足以翻转这个符号，用户看到的就是
 *  「胶囊来回弹跳」。4px 覆盖抖动，又不至于让「线上方 3px」的区块被误判。 */
const EPSILON = 4;

/** 程序化滚动（goTo）动画参数。 */
const EASE = 0.2; // 每帧走完剩余距离的 20%：1000px 约 520ms 收敛，与原生 smooth 同档
/** 末段吸附带（px）：进入这个距离就不再缓动，直接写目标值收尾。
 *  为什么需要：Chromium 会把小数 scrollTop 取整（headless dPR=1 实测
 *  写 1188.4 读回 1188）。距 maxScroll 还差 2px 时每帧只走 0.4px、被
 *  取整吃光，几何逼近永远收敛不了——实测 rAF 空转 7s+ 不退，看门狗又以
 *  「计算进度 0.4px」不停续期，动画永不收场（页面留一个 60fps 空转循环）。
 *  截断场景下目标恰是整数 maxScroll，一步写到底即脱离停机带
 *  （0.5, 2.5）px；未截断的小数目标写入后取整一次，残差 < 1px 无感。
 *  带宽取 4px 与 EPSILON 同档：覆盖取整坑，又不至于让「线附近 3px」的
 *  区块被提前判停。 */
const SNAP_PX = 4;
const ARRIVE_FRAMES = 2; // 连续这么多帧在吸附带内才算收敛（布局突变会让单帧差值先小后大）
const STALL_MS = 1200; // 停摆看门狗：有**实际**位移就续期，纯卡住 1.2s 强制收尾

interface NavAnim {
  id: string;
  host: ScrollHost;
  raf: number;
  still: number;
  timer: number;
}

/** 进行中的程序化滚动；null = 无动画（scroll-spy 正常工作）。模块级与
 *  cachedScroller 同理：切品类 / keep-alive 复用同一份状态。 */
let anim: NavAnim | null = null;

/** 显式跳转意图：goTo 的目标。停稳后不「终算一次」释放——maxScroll 截断下
 *  点击项可能被压在视口外（点倒数第二项滚到底），此时高亮必须留在点击项上，
 *  而不是被触底兜底改写成最后一项（实测：点「关联标的」高亮跑「更多数据」）。
 *  清除时机只有四种：用户自行滚动（滚轮 / 触摸 / 滚动键 / 拖滑块）、视口
 *  变化、品类切换、目标卸载。 */
let pinnedId: string | null = null;

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

  /** scroll-spy：最后一个越过定位线的区块为当前项；都在线下方时取第一项。
   *
   *  **程序化滚动期间不纠正**（anim 非空即返回）：位置由 goTo 的动画循环
   *  独占写，高亮已 pin 在目标上。若按当前实际位置继续纠正，落点压在
   *  定位线上时 ±0.5px 的亚像素抖动会让高亮在前一项与目标项之间反复
   *  翻跳——实测点「基金资料」停稳后高亮退回「交易记录」，约一半概率
   *  中招，即用户报的「来回弹跳、概率性跳对」。
   *
   *  **停稳后 pin 仍然有效**：显式点击的目标在用户接管前一直是当前项。
   *  没有它，maxScroll 截断下点倒数第二项会滚到底，下面的触底兜底随
   *  即把高亮改写成最后一项——点击意图被覆盖。 */
  function updateActive() {
    if (anim) return;
    if (pinnedId) {
      if (document.getElementById(pinnedId)) {
        activeId.value = pinnedId;
        return;
      }
      // 目标被卸载（品类切换 / 区块消失）：意图失效，落回 scroll-spy
      pinnedId = null;
    }
    const line = spyLine();
    let current = "";
    for (const item of items.value) {
      const el = document.getElementById(item.id);
      if (!el) continue;
      if (el.getBoundingClientRect().top <= line + EPSILON) current = item.id;
    }
    // 触底兜底（仅无 pin 时执行到这里）：最后一项下方没有更多内容把它推过
    // 定位线（maxScroll 截断，实测差 400-600px），按「越过线」判据它永远
    // 选不上——用户自己滚到底（或点最右侧胶囊，pin 同为目标项，结论一致），
    // 高亮却停在倒数第二项。滚到底时用户看的就是最后一项，与主流目录
    // （MDN / VitePress）行为一致。
    const metrics = scrollMetrics();
    if (
      metrics &&
      metrics.limit > 1 &&
      metrics.top >= metrics.limit - 1 &&
      items.value.length > 0
    ) {
      current = items.value[items.value.length - 1].id;
    }
    activeId.value = current || items.value[0]?.id || "";
  }

  /** 点击跳转：把目标区块顶边送到定位线处。
   *
   *  架构见文件头「单一滚动权威」。两个曾被实测的缺陷由此闭合：
   *  1. **过期目标**：原生 `scrollTo({behavior:'smooth'})` 终点只算一次，
   *     动画途中走势卡长高 300+px 会让终点整体失效（实测过冲 800+px）。
   *     故自绘 rAF 循环，每帧重读目标 rect，布局突变自适应；
   *  2. **高亮回跳**：落点正好压在定位线上，零容差 + scroll 事件纠正 →
   *     亚像素抖动来回翻。故 goTo 即置 active + pinnedId（pin），意图保持
   *     到用户自行滚动为止——停稳后只「终算一次」会被 maxScroll 截断场景
   *     下的触底兜底覆盖（见 pinnedId 注释）。
   */
  function goTo(id: string) {
    const el = document.getElementById(id);
    if (!el) return;
    cancelAnim(); // 连点：中止上一次，以最新一次为准
    activeId.value = id;
    pinnedId = id;
    const host = scrollHostFor(el);
    if (!host) return; // 内容不滚（比视口矮）：置了 active 即可

    const jumpTo = () => {
      const delta = el.getBoundingClientRect().top - spyLine();
      host.write(clamp(host.read() + delta, 0, host.limit()));
    };
    if (prefersReducedMotion()) {
      jumpTo();
      updateActive();
      return;
    }

    anim = { id, host, raf: 0, still: 0, timer: 0 };
    armStallWatchdog();
    step();
  }

  /** 动画帧：缓动逼近 + 每帧重读目标 + 收敛判定。 */
  function step() {
    if (!anim) return;
    const el = document.getElementById(anim.id);
    if (!el) {
      // 目标被卸载（品类切换 / 区块消失）：收尾，别把 pin 留在旧 id 上
      finishAnim();
      return;
    }
    const host = anim.host;
    const cur = host.read();
    // 每帧重读：布局突变时目标会整体移动，按旧布局算一次终点必然过期
    const delta = el.getBoundingClientRect().top - spyLine();
    const target = clamp(cur + delta, 0, host.limit());
    if (Math.abs(target - cur) < SNAP_PX) {
      // 末段吸附：写目标值本身（maxScroll 截断场景一步到底，避开取整停机带）
      host.write(target);
      anim.still += 1;
      if (anim.still >= ARRIVE_FRAMES) {
        finishAnim();
        return;
      }
    } else {
      anim.still = 0;
      const next = cur + (target - cur) * EASE;
      host.write(next);
      // 看门狗按**实际位移**续期：计算步长 > 0.1 但被取整吃掉时（写入
      // 1188.4 读回 1188），按计算值续期会永远续下去——动画空转不退。
      // 以写后读回值为准，真实停摆 1.2s 才强制收尾。
      if (Math.abs(host.read() - cur) > 0.1) armStallWatchdog();
    }
    anim.raf = requestAnimationFrame(step);
  }

  /** 停摆看门狗：动画因任何原因卡住（切标签页 rAF 暂停、目标卸载前的
   *  最后几帧……）时强制收尾——否则动画闸门永不释放、scroll-spy 永久失灵。 */
  function armStallWatchdog() {
    if (!anim) return;
    if (anim.timer) window.clearTimeout(anim.timer);
    anim.timer = window.setTimeout(finishAnim, STALL_MS);
  }

  /** 收尾：释放动画闸门。高亮以 pin 为准——pinnedId 在（用户点过胶囊、
   *  还没自行滚动）就保持点击意图；没有 pin 才按实测位置终算（EPSILON
   *  保证落点压在定位线上也算越过）。 */
  function finishAnim() {
    if (!anim) return;
    cancelAnim();
    updateActive();
  }

  function cancelAnim() {
    if (!anim) return;
    if (anim.raf) cancelAnimationFrame(anim.raf);
    if (anim.timer) window.clearTimeout(anim.timer);
    anim = null;
  }

  /** 用户接管：用户自己滚了（滚轮 / 触摸 / 滚动键 / 拖滑块）→ 意图让位，
   *  高亮按用户意志重算。pin 可能比动画活得更久（停稳后意图仍有效），
   *  故两种情况都清。自己的 scrollTop 写入不触发这几类事件，不会误伤
   *  自己的动画。 */
  function onUserIntent() {
    const hadIntent = anim !== null || pinnedId !== null;
    pinnedId = null;
    if (anim) cancelAnim();
    if (hadIntent) updateActive();
  }

  /** 只拦滚动类按键：输入框里的方向键不该取消动画（详情页有搜索场景）。 */
  const SCROLL_KEYS = new Set([
    "ArrowUp",
    "ArrowDown",
    "PageUp",
    "PageDown",
    "Home",
    "End",
    " "
  ]);
  function onKeydown(e: KeyboardEvent) {
    if (SCROLL_KEYS.has(e.key) && (anim || pinnedId)) onUserIntent();
  }

  /** 拖滚动条滑块也是用户接管：mousedown 落在 `.el-scrollbar__bar` 上即让位。
   *  滑块拖拽不触发 wheel / touchstart / keydown，只直接改 scrollTop——
   *  不拦它，动画剩余几帧会把 thumb 拽回目标位置（用户感觉拽不动）。
   *  停稳后的拖拽同样要清 pin（不能因 `if (!anim) return` 把意图留下）。 */
  function onMousedown(e: MouseEvent) {
    const target = e.target as HTMLElement | null;
    if (target?.closest?.(".el-scrollbar__bar")) onUserIntent();
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
    // 视口宽度变化可能切换滚动宿主 / 侧边栏折叠，定位线随之变；
    // 进行中的跳转目标与已 pin 的意图都已失效（新布局下区块位置全变）
    // → 中止动画、清 pin，让 scroll-spy 按新布局重算，用户重新点击即可。
    cancelAnim();
    pinnedId = null;
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
    // 用户接管监听：动画途中用户自己滚了就立即让位（见 onUserIntent）。
    // 自己的 scrollTop 写入不触发这三类事件，不会误伤自己的动画。
    document.addEventListener("wheel", onUserIntent, {
      capture: true,
      passive: true
    });
    document.addEventListener("touchstart", onUserIntent, {
      capture: true,
      passive: true
    });
    document.addEventListener("mousedown", onMousedown, { capture: true });
    document.addEventListener("keydown", onKeydown, { capture: true });
  });

  onDeactivated(() => {
    // keep-alive 缓存期间不留后台动画（rAF 对不可见页面仍可能触发），
    // 顺带清掉跳转意图——恢复时由 onActivated 按还原后的位置重算
    cancelAnim();
    pinnedId = null;
  });

  onActivated(() => {
    // keep-alive 恢复时滚动位置可能已被浏览器还原，active 需重算
    scan();
    updateActive();
  });

  onBeforeUnmount(() => {
    document.removeEventListener("scroll", onScroll, { capture: true });
    window.removeEventListener("resize", onResize);
    document.removeEventListener("wheel", onUserIntent, { capture: true });
    document.removeEventListener("touchstart", onUserIntent, {
      capture: true
    });
    document.removeEventListener("mousedown", onMousedown, { capture: true });
    document.removeEventListener("keydown", onKeydown, { capture: true });
    observer?.disconnect();
    if (rafId) cancelAnimationFrame(rafId);
    cancelAnim();
    pinnedId = null;
    cachedScroller = undefined;
  });

  // 品类切换（基金 → 股票等）：等 patch 完再扫，否则读到的是上一页的 DOM；
  // 旧品类的跳转意图一并作废（updateActive 里按 id 找不到元素也会自愈，
  // 这里显式清，避免「容器还没重建」的窗口期内 pin 指向上一个品类）
  watch(product, () => {
    pinnedId = null;
    nextTick(scan);
  });

  return { items, activeId, goTo };
}
