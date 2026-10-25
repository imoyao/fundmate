import type { DistributionsData } from "@/api/summary";

/**
 * 资产大类**构成柱状图**的纯计算部分（option 组装）。
 *
 * ## 为什么是柱状图，不是瀑布图（本文件的前身 `assetWaterfall.ts` 已删除）
 *
 * 这张卡的标题是「资产大类」，它要回答的是「我有哪些资产、各多少」——一个**构成**
 * 问题，靠**柱长**比较。瀑布图回答的是另一个问题：「从一个起点经过若干笔增减落到
 * 终点」，柱长 = 变动量、柱位 = 累计水位。把它用在这里会带来两处结构性误读：
 *
 * 1. **位置取代长度成为读数依据**：投资理财（51.79 万）比流动资金（99.38 万）柱子**短**、
 *    位置却**更高**，第一眼会被读成"更大"；
 * 2. **信息重复**：左卡已经给出总资产 / 总负债 / 净资产三个数字，右卡再画一遍"净资产
 *    是怎么来的"，同一份结论在一个视口里出现两次（#2034 / #2150 反复裁决的
 *    「先问能不能去掉」）。
 *
 * 故本图只画**资产端各大类**，一律从 0 起、按金额降序；负债与净资产留在左卡。
 *
 * ## 边界
 *
 * **只做纯计算**：不碰 echarts 实例、不碰 DOM、不读响应式、不读 CSS 变量
 *（颜色由调用方解析后传入——canvas 的 `fillStyle` 不认 `var(--x)`）。
 * 实例生命周期与两态切换时序留在 `OverviewSummaryCard.vue`（#2164 / #1925 的契约）。
 */

/** 一根构成柱：只保留画图需要的两个字段。 */
export interface CompositionItem {
  name: string;
  value: number;
}

/** 该行主题下用到的语义色，全部由调用方从 CSS 变量读出后传入（本模块不碰 DOM）。 */
export interface CompositionColors {
  /** 柱体填充：资产端用 `--color-rise`，与左卡「涨」同色系 */
  bar: string;
  /**
   * 柱顶金额的字色，取 `-ink` 级（design.md：柱体用 rise/fall 填充，柱上文字用
   * `-ink` 才达 AA）。⚠️ 必须是**解析后**的值，不能是 `var(--x)`。
   */
  barInk: string;
  /** 轴标签色。design.md：凡 `color:` 用途一律走 `--text-tertiary-ink` */
  axis: string;
  /** 网格线色 */
  border: string;
  /** x 轴底线色。它同时是"0 基线"，取比网格线深一档的 `--border-default` */
  axisLine: string;
}

/**
 * 轴上限相对最大值的余量系数。
 *
 * 存在的唯一理由是**柱顶标签**：标签画在柱子上方（`position: "top"`），若轴上限
 * 正好压在最大值上，最高那根柱的标签会顶出绘图区——本卡前身（瀑布图）的
 * 「应收款标注跑到 400 万刻度线以上」正是这个缺陷。留 18% 的空白即可容纳
 * 一行 11px 文字，且不会让柱子看起来被压扁。
 */
const TOP_HEADROOM = 1.18;

/**
 * 期望的纵轴格数。
 *
 * 取 6 而不是 4：格数太少时步长会跳到「整 100 万」，一条网格线跨掉一大截，
 * 4 根柱子只剩 3 条线可比高矮。6 格能稳定落在 50 万这一档。
 */
const TARGET_SPLITS = 6;

/**
 * 取一个「整数档」的刻度步长（1 / 2 / 2.5 / 5 × 10ⁿ）。
 *
 * 轴上限自己算而不是交给 echarts 自动：自动刻度会随「多一分钱」换档，
 * 同一份数据两次刷新可能刻度不同，柱子高度看起来会"跳"。
 */
function niceStep(raw: number): number {
  if (!(raw > 0) || !Number.isFinite(raw)) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude; // [1, 10)
  const multiplier =
    normalized <= 1
      ? 1
      : normalized <= 2
        ? 2
        : normalized <= 2.5
          ? 2.5
          : normalized <= 5
            ? 5
            : 10;
  return multiplier * magnitude;
}

/** 轴标签：短、不带 ¥（轴是标尺，不是金额），过万按万 / 亿缩写 */
function formatAxis(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e8) return `${(value / 1e8).toFixed(1)}亿`;
  if (abs >= 1e4) {
    const wan = value / 1e4;
    // 整数万不写小数：步长 50 万时写出「50.0万」纯属噪声，而 2.5 万这类
    // 半档（niceStep 的 2.5 分支）又必须保留一位
    return `${Number.isInteger(wan) ? wan.toFixed(0) : wan.toFixed(1)}万`;
  }
  return String(Math.round(value));
}

/**
 * 柱顶金额：带 ¥、过万缩写，保证一行放得下。
 * 负号只在 `¥` 之前产生一次（design.md「数字格式规范」）。
 */
function formatBarLabel(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}¥${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${sign}¥${(abs / 1e4).toFixed(2)}万`;
  return `${sign}¥${abs.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`;
}

/** tooltip：完整精度，不缩写（用户是来读确切数字的） */
function formatExact(value: number): string {
  return `¥${value.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`;
}

/**
 * 从后端 distributions 取出要画的柱子：**只取资产大类，降序，过滤非正值**。
 *
 * - **不含负债**：负债单独成柱会把纵轴压成「上半截资产、下半截负债」，
 *   5 万的应收款在 176 万的负柱旁边只剩一条扁线（实测），比较功能反而失效；
 * - **降序**：构成图的读法是「从大到小」，顺序本身承担一部分信息；
 * - **过滤 0 / 负数**：0 值柱在图上不可见却占一个类目位，留白比画出来更诚实；
 * - **不改入参**：`[...]` 复制后再 sort，调用方的响应式数据不能被就地重排。
 */
export function compositionItems(
  distributions: DistributionsData
): CompositionItem[] {
  return (distributions.category_distribution ?? [])
    .filter(c => Number.isFinite(c.value) && c.value > 0)
    .map(c => ({ name: c.name, value: c.value }))
    .sort((a, b) => b.value - a.value);
}

/** 没有可画的资产大类时返回 false，调用方据此跳过 `setOption`（不画全 0 的空图） */
export function hasCompositionData(distributions: DistributionsData): boolean {
  return compositionItems(distributions).length > 0;
}

/**
 * 组装构成柱状图 option。
 *
 * ⚠️ **不接收高度**：本图没有任何按像素判定的逻辑（前身瀑布图要为极小值柱算引线），
 * 容器高度只影响绘图区大小，由 echarts 的 `resize()` 自己处理。
 */
export function buildCompositionOption(
  items: CompositionItem[],
  colors: CompositionColors
) {
  const max = items.reduce((m, i) => Math.max(m, i.value), 0);
  // 目标值先加余量，再切成 TARGET_SPLITS 份取整数档步长；上限按同一步长向上取整，
  // 这样最后一格必定落在 max 之外（不会出现「数据顶到边界、刻度压在柱顶上」）
  const step = niceStep((max * TOP_HEADROOM) / TARGET_SPLITS);
  const axisMax = Math.max(step, Math.ceil((max * TOP_HEADROOM) / step) * step);

  return {
    backgroundColor: "transparent",
    // 动画关掉：本卡两态（构成图 / 收益日历）是原地切换，切换时再放动画会让
    // 卡片高度与底边对齐闪一下
    animation: false,
    tooltip: {
      trigger: "axis" as const,
      axisPointer: { type: "shadow" as const },
      valueFormatter: (v: unknown) =>
        typeof v === "number" ? formatExact(v) : String(v)
    },
    grid: {
      // 四边都留够：left 给轴标签，top 给柱顶金额（含 TOP_HEADROOM 的视觉余量）
      left: 8,
      right: 12,
      top: 24,
      bottom: 4,
      containLabel: true
    },
    xAxis: {
      type: "category" as const,
      data: items.map(i => i.name),
      // 类目只有 4 个左右，逐个显示；hideOverlap 兜住窄断点下的拥挤
      axisLabel: {
        interval: 0,
        hideOverlap: true,
        margin: 10,
        fontSize: 11,
        color: colors.axis
      },
      // x 轴这条线同时是「0 基线」：它必须能看见，否则柱子又变成"悬空"的
      axisLine: { lineStyle: { color: colors.axisLine } },
      axisTick: { show: false }
    },
    yAxis: {
      type: "value" as const,
      // 从 0 起：构成长的唯一含义就是「与 0 的差」
      min: 0,
      max: axisMax,
      interval: step,
      splitLine: { lineStyle: { color: colors.border } },
      axisLabel: { color: colors.axis, fontSize: 11, formatter: formatAxis }
    },
    series: [
      {
        name: "资产大类",
        type: "bar" as const,
        barMaxWidth: 40,
        // 极小金额仍留一丝可见高度：5 万在 376 万量级下只有几像素，
        // 画成 0 就等于说"没有这一项"（本产品红线：缺数据不可画成 0）
        barMinHeight: 2,
        data: items.map(i => i.value),
        itemStyle: {
          color: colors.bar,
          // 只圆上两角：底部贴住 0 轴，圆角会把"从 0 起"这个事实削掉
          borderRadius: [4, 4, 0, 0] as [number, number, number, number]
        },
        label: {
          show: true,
          position: "top" as const,
          distance: 6,
          fontSize: 11,
          fontWeight: 600,
          color: colors.barInk,
          formatter: (p: { value: number }) => formatBarLabel(p.value)
        }
      }
    ]
  };
}
