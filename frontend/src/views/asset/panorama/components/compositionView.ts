import type { DistributionsData } from "@/api/summary";
import { getCssVar } from "@/composables/echarts/theme";

import {
  type CompositionColors,
  buildCompositionOption,
  compositionItems
} from "./assetComposition";

/**
 * 构成柱状图的「取色 + 组装 option」。
 *
 * 与 `assetComposition.ts` 分工：那边是纯计算（不碰 DOM），这边负责**读 CSS 变量**
 * 并把它递给纯计算。为什么拆两层：本卡文件在 `scripts/check_vue_size.mjs` 的基线内
 * （#980，只减不增），注释比逻辑长；而实例时序（init / dispose / 主题重绘）必须
 * 留在调用方——`useEchartsLifecycle` 与 `toggleCalendar` 的 `nextTick` 顺序是
 * #2164 / #1925 的契约。
 */

/**
 * 读出一整套构成图语义色。
 *
 * ⚠️ 一律取**解析后**的颜色值，不能把 `var(--x)` 递下去：echarts 画在 canvas 上，
 * `fillStyle` 不认 CSS 变量——赋值会被静默忽略、退回上一次的 fillStyle，
 * 症状是「标签颜色时灰时绿、与柱无关」。暗色主题由 `useEchartsLifecycle` 在
 * 主题切换时重建实例、重跑本函数，故这里读到的仍是当前主题的值。
 */
export function readCompositionColors(): CompositionColors {
  return {
    bar: getCssVar("--color-rise"),
    // 柱顶文字走 -ink 级（--color-rise 在白卡上做文字只有 3.6:1，达不到 AA）
    barInk: getCssVar("--color-rise-ink"),
    // 轴标签也是文字：design.md 规定 `color:` 用途一律走 --text-tertiary-ink
    //（--text-tertiary 白底仅 3.69:1）
    axis: getCssVar("--text-tertiary-ink"),
    border: getCssVar("--border-light"),
    // 0 基线要比网格线深一档：--border-light 在白卡上只有约 1.1:1，
    // 柱子底部那条线等于没画，"从 0 起"这个事实就丢了
    axisLine: getCssVar("--border-default")
  };
}

/** 组装 option：数据整形（`compositionItems`）与取色各做一半，这里只负责拼起来 */
export function buildCompositionViewOption(distributions: DistributionsData) {
  return buildCompositionOption(
    compositionItems(distributions),
    readCompositionColors()
  );
}
