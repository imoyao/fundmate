// src/composables/useTweenNumber.ts
/**
 * 数字缓动（盘中行情刷新时用）：数值变化走 420ms ease-out，而不是每 30s 硬跳一次。
 *
 * 三条刻意做成这样的取舍（「不打扰」的落地口径）：
 *
 * 1. **首值直接落地，绝不从 0 滚上去**——从 0 滚到 +1,227.88 会被读成
 *    「今天赚了一千二」，那是编造一次不存在的波动；
 * 2. **只动数字本身**：不闪背景、不呼吸、不 toast、不播报；颜色/箭头由调用方
 *    按新值渲染，不参与动画（否则每轮刷新屏幕都在红绿之间抽搐）；
 * 3. **尊重 `prefers-reduced-motion`**：系统关掉动效的用户直接看到新值。
 *
 * 用 `requestAnimationFrame` 而非 CSS transition：金额是文本节点、宽度随位数变化，
 * CSS 过渡只能动 opacity/transform，动不了数值本身（那会变成「淡入一个新数字」，
 * 比硬跳更容易被误读成刷新了整张卡）。
 */

import { onBeforeUnmount, ref, watch, type Ref } from "vue";

/** ease-out-cubic：前段快、末段稳，读数的注意力不会被拖住 */
export function easeOutCubic(t: number): number {
  const clamped = Math.min(1, Math.max(0, t));
  return 1 - Math.pow(1 - clamped, 3);
}

export interface TweenNumberOptions {
  /** 动画时长（ms）；默认 420，短于一次行情刷新间隔 */
  duration?: number;
  /** 小于该差值直接落值（分以下的抖动没有展示意义） */
  epsilon?: number;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * @param source 目标值（null = 无数据，直接渲染占位，不做动画）
 * @returns 用于展示的缓动值
 */
export function useTweenNumber(
  source: Ref<number | null | undefined>,
  options: TweenNumberOptions = {}
): Ref<number | null> {
  const duration = options.duration ?? 420;
  const epsilon = options.epsilon ?? 0.005;
  const display = ref<number | null>(source.value ?? null);

  let frame = 0;
  let from = 0;
  let to = 0;
  let startedAt = 0;

  const cancel = () => {
    if (frame) {
      cancelAnimationFrame(frame);
      frame = 0;
    }
  };

  const step = (now: number) => {
    const progress = duration > 0 ? (now - startedAt) / duration : 1;
    if (progress >= 1) {
      display.value = to;
      frame = 0;
      return;
    }
    display.value = from + (to - from) * easeOutCubic(progress);
    frame = requestAnimationFrame(step);
  };

  watch(source, next => {
    const target = next ?? null;
    if (target === null) {
      cancel();
      display.value = null;
      return;
    }
    const current = display.value;
    // 首值 / 无动效偏好 / 变化太小：直接落值
    if (
      current === null ||
      prefersReducedMotion() ||
      Math.abs(target - current) < epsilon
    ) {
      cancel();
      display.value = target;
      return;
    }
    cancel();
    from = current;
    to = target;
    startedAt = performance.now();
    frame = requestAnimationFrame(step);
  });

  onBeforeUnmount(cancel);

  return display;
}
