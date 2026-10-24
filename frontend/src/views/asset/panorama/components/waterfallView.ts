import type { DistributionsData } from "@/api/summary";
import { getCssVar } from "@/composables/echarts/theme";

import {
  type WaterfallColors,
  buildWaterfallBars,
  buildWaterfallOption
} from "./assetWaterfall";

/**
 * 瀑布图的「取色 + 组装 option」。
 *
 * 为什么从 `OverviewSummaryCard.vue` 里搬出来：那个文件在 `scripts/check_vue_size.mjs`
 * 的基线内（#980，基准 469 行，只减不增），而这段代码注释比逻辑还长。边界与
 * `assetWaterfall.ts` 同款——**只做取色与组装，不碰实例、不碰 DOM 时序**：
 * init / dispose / 主题重绘仍留在调用方（`useEchartsLifecycle` 的时序是 #2164 的契约）。
 */

/**
 * 读出一整套瀑布图语义色。
 *
 * ⚠️ 一律取**解析后**的颜色值，不能把 `var(--x)` 递下去：echarts 画在 canvas 上，
 * `fillStyle` 不认 CSS 变量——赋值会被静默忽略、退回上一次的 fillStyle，症状是
 * 「标签颜色时灰时绿、与柱无关」。tooltip 走 HTML 才吃变量；这里统一用解析值，
 * 两条出口的颜色才必然一致。
 */
export function readWaterfallColors(): WaterfallColors {
  return {
    rise: getCssVar("--color-rise"),
    fall: getCssVar("--color-fall"),
    info: getCssVar("--color-info"),
    neutral: getCssVar("--color-neutral"),
    // 轴标签也是文字：design.md 规定 `color:` 用途一律走 --text-tertiary-ink
    //（--text-tertiary 白底仅 3.69:1，达不到正文 4.5:1）
    axis: getCssVar("--text-tertiary-ink"),
    border: getCssVar("--border-light"),
    // 连接线取 --text-tertiary：colors.css 把它定义为「辅助底色/描边/图形」级，
    // 正好是瀑布台阶的语义。--border-default 在白卡上只有 ~11% 明度差，
    // 1px 虚线实际看不见（实测），等于白画。
    connector: getCssVar("--text-tertiary"),
    riseInk: getCssVar("--color-rise-ink"),
    fallInk: getCssVar("--color-fall-ink"),
    neutralInk: getCssVar("--text-secondary"),
    primaryInk: getCssVar("--text-primary"),
    // 极小值标注条的垫底色 = 卡片底色：它压在绘图区上，没有垫底就会与网格线、
    // 相邻柱体的边缘糊在一起（暗色自动跟随令牌）
    surface: getCssVar("--bg-card")
  };
}

/**
 * 组装瀑布图 option。
 *
 * `heightPx` 由调用方从容器读出：极小值柱按**像素高度**判定（`assetWaterfall.ts` 的
 * `TINY_BAR_PX`），而那个模块不碰 DOM。**宽度刻意不传**——`chart.resize()` 只重排、
 * 不会重跑本函数，按宽度算出来的结论在缩放后必然失真（详见 `WaterfallLayout` 注释）。
 */
export function buildWaterfallViewOption(
  distributions: DistributionsData,
  heightPx: number
) {
  return buildWaterfallOption(
    buildWaterfallBars(distributions),
    readWaterfallColors(),
    { height: heightPx }
  );
}
