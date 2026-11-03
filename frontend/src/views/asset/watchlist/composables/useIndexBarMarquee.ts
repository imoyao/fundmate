/**
 * 大盘指数条折叠态的「单行跑马灯」（#watchlist 顶部指数条）。
 *
 * 只负责三件事：测量内容宽、判是否启用、算一圈时长。暂停与动画本身交给 CSS
 * （`:hover` / `:focus-within` 暂停）——用 JS 定时器暂停会让「鼠标停在某项上
 * 读点位」这件事变得不可靠。
 *
 * 启用条件（两者同时满足）：
 *   1. 内容溢出容器（几项放得下时静态，见 `shouldMarquee`）；
 *   2. 用户没有关掉「滚动展示」开关（设置弹窗里可关），且系统未要求减弱动效
 *      （`prefers-reduced-motion: reduce`）。
 *
 * ⚠️ 刻意**不**按交易时段开关（2026-11-03 修正）：
 *   初版加了 `isWithinTradingWindow`，理由是「收盘后价格不动，静态更安静」。
 *   实机验证 16:15 打开自选页，看到的是可横向滚动的静态条——对用户而言就是
 *   「跑马灯没生效、还是那条滚动条」，比一直在动更糟。一个在一天里 2/3 时间
 *   表现为失效的开关，收益远小于误解成本；想让它彻底不动，用设置里的开关。
 *
 * 模板契约：容器的**第一个** `.index-market-bar__group` 元素代表一份完整内容；
 * 启用跑马灯时模板会再渲染一份（`aria-hidden` + `tabindex=-1`）用于无缝循环。
 */
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
  type Ref
} from "vue";
import type { CSSProperties } from "vue";
import {
  MARQUEE_SPEED_PX_PER_SEC,
  marqueeDurationSeconds,
  shouldMarquee
} from "@/views/asset/watchlist/composables/indexBarModel";

const GROUP_SELECTOR = ".index-market-bar__group";

export interface IndexBarMarquee {
  /** 绑到滚动容器上 */
  containerRef: Ref<HTMLElement | null>;
  /** 是否启用跑马灯（false = 静态，可能仍可横向滚动） */
  active: Ref<boolean>;
  /** 渲染几份内容：1 份静态，2 份无缝循环 */
  copies: Ref<number[]>;
  /** 传给 track 的 CSS 变量（位移距离 / 一圈时长） */
  trackStyle: Ref<CSSProperties>;
}

/**
 * @param items   渲染项（变化时重新测量宽度）
 * @param enabled 用户是否开启「滚动展示」（设置弹窗里的开关）
 */
export function useIndexBarMarquee(
  items: Ref<unknown[]>,
  enabled: Ref<boolean>
): IndexBarMarquee {
  const containerRef = ref<HTMLElement | null>(null);
  const active = ref(false);
  const contentWidth = ref(0);
  const durationSec = ref(0);

  let observer: ResizeObserver | null = null;
  let motionQuery: MediaQueryList | null = null;

  function prefersReducedMotion(): boolean {
    return Boolean(motionQuery?.matches);
  }

  function measure(): void {
    const container = containerRef.value;
    if (!container) {
      active.value = false;
      return;
    }
    const group = container.querySelector<HTMLElement>(GROUP_SELECTOR);
    if (!group) {
      active.value = false;
      return;
    }
    const width = group.offsetWidth;
    contentWidth.value = width;
    active.value =
      enabled.value &&
      !prefersReducedMotion() &&
      shouldMarquee(width, container.clientWidth);
    durationSec.value = active.value
      ? marqueeDurationSeconds(width, MARQUEE_SPEED_PX_PER_SEC)
      : 0;
  }

  function onMotionPreferenceChange(): void {
    measure();
  }

  onMounted(() => {
    motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    motionQuery.addEventListener("change", onMotionPreferenceChange);

    const container = containerRef.value;
    if (container) {
      observer = new ResizeObserver(() => measure());
      observer.observe(container);
      const group = container.querySelector<HTMLElement>(GROUP_SELECTOR);
      if (group) observer.observe(group);
    }
    measure();
  });

  onBeforeUnmount(() => {
    observer?.disconnect();
    observer = null;
    motionQuery?.removeEventListener("change", onMotionPreferenceChange);
    motionQuery = null;
  });

  // 选中集合变化（增删指数）→ DOM 更新后再量一次：宽度变了，圈时长也得跟着变
  watch(items, measure, { deep: true, flush: "post" });
  // 用户拨动「滚动展示」开关 → 立即切换形态
  watch(enabled, measure, { flush: "post" });

  const copies = computed(() => (active.value ? [0, 1] : [0]));

  const trackStyle = computed<CSSProperties>(
    () =>
      ({
        "--marquee-shift": `-${contentWidth.value}px`,
        "--marquee-duration": `${durationSec.value}s`
      }) as CSSProperties
  );

  return { containerRef, active, copies, trackStyle };
}
