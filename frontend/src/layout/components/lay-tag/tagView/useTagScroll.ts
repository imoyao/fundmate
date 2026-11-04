/**
 * 标签栏的横向滚动（#980 拆分自 layout/components/lay-tag/index.vue）。
 *
 * 这块的难点全在**纯算术**上：让当前激活的标签滚进可视区、滚轮按像素平滑推进、
 * 两头都别滚过头。原实现把它们和 DOM 取值、`instance.refs` 搅在一起，只能手点验证。
 * 这里拆成「纯函数算目标值 + 组合式负责取 DOM 与写回」，纯函数部分可直接断言。
 */

import { nextTick, ref } from "vue";
import type { Ref } from "vue";
import { isAllEmpty, isEqual } from "@pureadmin/utils";

/** 标签滚到可视区后，与左右边缘之间留的间距（px） */
export const TAB_NAV_PADDING = 10;
/** 平滑滚动每帧推进的像素 */
export const SCROLL_STEP = 20;

export interface TabScrollMetrics {
  /** 可视容器宽度（不含溢出部分） */
  viewWidth: number;
  /** 标签总宽度（含溢出部分） */
  tabTotalWidth: number;
  /** 目标标签相对标签容器的左偏移 */
  tabLeft: number;
  /** 目标标签自身宽度 */
  tabWidth: number;
}

/**
 * 让目标标签滚进可视区，返回新的 `translateX` 与箭头显隐。
 *
 * 四种情形逐条对齐原实现：待滚的标签在左边界外、在可视区内、在右边界外，
 * 以及「标签总宽没超过容器（不需要滚动）」。
 */
export function resolveTabScroll(
  metrics: TabScrollMetrics,
  current: number
): { translateX: number; isShowArrow: boolean } {
  const { viewWidth, tabTotalWidth, tabLeft, tabWidth } = metrics;
  // 标签总宽超过容器才需要左右箭头
  const isShowArrow = viewWidth <= tabTotalWidth;
  if (tabTotalWidth < viewWidth || tabLeft === 0) {
    return { translateX: 0, isShowArrow };
  }
  if (tabLeft < -current) {
    // 标签在可视区左侧：把它拉到左边缘（留间距）
    return { translateX: -tabLeft + TAB_NAV_PADDING, isShowArrow };
  }
  if (tabLeft > -current && tabLeft + tabWidth < -current + viewWidth) {
    // 标签已经在可视区里：只做「不让它顶到右边缘」的收敛
    return {
      translateX: Math.min(0, viewWidth - tabWidth - tabLeft - TAB_NAV_PADDING),
      isShowArrow
    };
  }
  // 标签在可视区右侧：把它拉到右边缘（留间距）
  return {
    translateX: -(tabLeft - (viewWidth - TAB_NAV_PADDING - tabWidth)),
    isShowArrow
  };
}

/**
 * 按偏移量推进滚动位置，并把结果夹在 [容器宽 - 标签总宽, 0] 区间内。
 *
 * 注意到这里的分支形状是刻意的：**已经滚到最左且继续往左滚时原值不变**，
 * 「标签没超宽」时才强制归零——两种情形混起来写会让超宽时的回弹看着像抖动。
 */
export function clampTranslate(
  offset: number,
  current: number,
  metrics: { viewWidth: number; tabTotalWidth: number }
): number {
  const { viewWidth, tabTotalWidth } = metrics;
  if (offset > 0) return Math.min(0, current + offset);
  if (viewWidth >= tabTotalWidth) return 0;
  if (current < -(tabTotalWidth - viewWidth)) return current;
  return Math.max(current + offset, viewWidth - tabTotalWidth);
}

/** 滚轮 → 滚动偏移量：横向滚轮决定方向，强度取两轴绝对值之和 */
export function wheelOffset(deltaX: number, deltaY: number): number {
  const intensity = Math.abs(deltaX) + Math.abs(deltaY);
  if (deltaX < 0) return intensity > 0 ? intensity : 100;
  return intensity > 0 ? -intensity : -100;
}

/**
 * 标签栏滚动的组合式。
 *
 * `instance` 必须传组件实例：标签的 `ref="'dynamic' + index"` 是**动态字符串 ref**，
 * 只有 `instance.refs` 能拿到；换成 `useTemplateRef` 取不到这种按 index 生成的引用。
 */
export function useTagScroll(options: {
  instance: any;
  route: any;
  multiTags: Ref<any[]>;
  translateX: Ref<number>;
  isScrolling: Ref<boolean>;
}) {
  const { instance, route, multiTags, translateX, isScrolling } = options;

  const tabDom = ref<HTMLDivElement>();
  const containerDom = ref<HTMLDivElement>();
  const scrollbarDom = ref<HTMLDivElement>();
  const isShowArrow = ref(false);

  const metricsOf = (): { viewWidth: number; tabTotalWidth: number } => ({
    viewWidth: scrollbarDom.value ? scrollbarDom.value.offsetWidth : 0,
    tabTotalWidth: tabDom.value ? tabDom.value.offsetWidth : 0
  });

  const moveToView = async (index: number): Promise<void> => {
    await nextTick();
    if (!instance.refs["dynamic" + index]) return;
    const tabItemEl = instance.refs["dynamic" + index][0] as HTMLElement;
    if (!tabItemEl) return;
    const next = resolveTabScroll(
      {
        ...metricsOf(),
        tabLeft: tabItemEl.offsetLeft,
        tabWidth: tabItemEl.offsetWidth
      },
      translateX.value
    );
    isShowArrow.value = next.isShowArrow;
    translateX.value = next.translateX;
  };

  /** 对齐当前路由对应的标签：路由变化、窗口尺寸变化、挂载后都要调一次 */
  const dynamicTagView = async (): Promise<void> => {
    await nextTick();
    const index = multiTags.value.findIndex(item => {
      if (!isAllEmpty(route.query)) return isEqual(route.query, item.query);
      if (!isAllEmpty(route.params)) return isEqual(route.params, item.params);
      return route.path === item.path;
    });
    await moveToView(index);
  };

  const handleScroll = (offset: number): void => {
    translateX.value = clampTranslate(offset, translateX.value, metricsOf());
    isScrolling.value = false;
  };

  /** 按帧推进，直到把这次滚轮的偏移量走完 */
  const smoothScroll = (offset: number): void => {
    let remaining = Math.abs(offset);
    const scrollStep = () => {
      const scrollOffset = Math.sign(offset) * Math.min(SCROLL_STEP, remaining);
      handleScroll(scrollOffset);
      remaining -= Math.abs(scrollOffset);
      if (remaining > 0) requestAnimationFrame(scrollStep);
    };
    requestAnimationFrame(scrollStep);
  };

  const handleWheel = (event: WheelEvent): void => {
    isScrolling.value = true;
    smoothScroll(wheelOffset(event.deltaX, event.deltaY));
  };

  return {
    tabDom,
    containerDom,
    scrollbarDom,
    isShowArrow,
    moveToView,
    dynamicTagView,
    handleScroll,
    handleWheel
  };
}
