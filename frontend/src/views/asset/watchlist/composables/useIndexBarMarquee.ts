/**
 * 大盘指数条折叠态的「单行跑马灯」（#watchlist 顶部指数条）。
 *
 * 只负责三件事：测量内容宽、判是否启用、算一圈时长。暂停与动画本身交给 CSS
 * （`:hover` / `:focus-within` 暂停）——用 JS 定时器暂停会让「鼠标停在某项上
 * 读点位」这件事变得不可靠。
 *
 * 启用条件（三者同时满足）：
 *   1. 内容溢出容器（几项放得下时静态，见 `shouldMarquee`）；
 *   2. 处于 A 股交易时段（`isWithinTradingWindow`）——收盘后价格不动，静态更安静；
 *   3. 用户没有 `prefers-reduced-motion: reduce`。
 * 不满足时退回「可横向滚动的静态条」，溢出内容仍能看全（细滚动条，hover 才显色）。
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
import { isWithinTradingWindow } from "@/utils/marketHours";
import {
  MARQUEE_SPEED_PX_PER_SEC,
  marqueeDurationSeconds,
  shouldMarquee
} from "@/views/asset/watchlist/composables/indexBarModel";

/** 交易时段边界只在开盘/收盘两个时刻变化，每分钟复核一次足够 */
const SESSION_RECHECK_MS = 60_000;

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

export function useIndexBarMarquee(items: Ref<unknown[]>): IndexBarMarquee {
  const containerRef = ref<HTMLElement | null>(null);
  const active = ref(false);
  const contentWidth = ref(0);
  const durationSec = ref(0);

  let observer: ResizeObserver | null = null;
  let sessionTimer: number | null = null;
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
      !prefersReducedMotion() &&
      isWithinTradingWindow(new Date()) &&
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
    sessionTimer = window.setInterval(measure, SESSION_RECHECK_MS);
    measure();
  });

  onBeforeUnmount(() => {
    observer?.disconnect();
    observer = null;
    if (sessionTimer !== null) {
      clearInterval(sessionTimer);
      sessionTimer = null;
    }
    motionQuery?.removeEventListener("change", onMotionPreferenceChange);
    motionQuery = null;
  });

  // 选中集合变化（增删指数）→ DOM 更新后再量一次：宽度变了，圈时长也得跟着变
  watch(items, measure, { deep: true, flush: "post" });

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
