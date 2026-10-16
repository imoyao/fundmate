import type { DistributionsData } from "@/api/summary";

/**
 * 资产大类瀑布图的**纯计算**部分（图表 option 与柱几何）。
 *
 * 为什么不留在 `OverviewSummaryCard.vue` 里：那个文件要同时管左卡排版、右卡两态
 * 切换、`toggleCalendar` 的 DOM 时序与主题重绘。加上瀑布几何与格式化后单文件超
 * 600 行，撞破 `scripts/check_vue_size.mjs` 的 400 行软阈值（#980 治本项）。
 * 本仓的既有先例是 `PnlCalendarBars` 从 `PnlCalendar` 拆出，理由相同。
 *
 * 边界：**只做纯计算**，不碰 echarts 实例、不碰 DOM、不读响应式。
 * 实例生命周期（init / dispose / 主题重绘）与两态切换时序留在调用方，
 * 因为 `toggleCalendar` 的 `nextTick()` 顺序是 #1925 的行为契约，不能被搬走。
 */

/** 一根瀑布柱的语义。 */
export interface WaterfallBar {
  name: string;
  /** 透明基座高度：柱体从这条线往上长，视觉上「悬」在它的累计值上 */
  base: number;
  /** 柱体自身高度（恒 ≥ 0；正负由 base 决定柱体朝上还是朝下） */
  delta: number;
  /** 该步净变动（有符号）：标签与 tooltip 用 */
  change: number;
  /** 走到这一步之后的累计值：tooltip 用 */
  cumulative: number;
  /** 终点柱（净资产）：从 0 起算，代表最终结余而非某一步的增量 */
  isEndpoint: boolean;
}

/** 该行主题下要用到的语义色，全部由调用方从 CSS 变量读出后传入（本模块不碰 DOM） */
export interface WaterfallColors {
  rise: string;
  fall: string;
  info: string;
  neutral: string;
  textSecondary: string;
  /** 轴标签色。design.md：凡 `color:` 用途一律走 --text-tertiary-ink */
  axis: string;
  border: string;
}

/**
 * 柱标签的字色。终点柱用主文字色，涨跌柱用各自的 `-ink` 级
 * （与 `PnlCalendarTile` 的 `textColor` 同一套口径：底色浅，文字才用 -ink 达标）。
 */
const INK_RISE = "var(--color-rise-ink)";
const INK_FALL = "var(--color-fall-ink)";
const INK_NEUTRAL = "var(--text-secondary)";
const INK_PRIMARY = "var(--text-primary)";

/** echarts 回调里只用到 dataIndex，声明最小结构即可，不必引入 any */
interface BarParam {
  dataIndex: number;
}
type TooltipParam = BarParam | BarParam[];

/** tooltip 里要回显分类名（后端数据），插值前先转义 */
const ESCAPE_MAP: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
};
function escapeHtml(raw: string): string {
  return raw.replace(/[&<>"']/g, c => ESCAPE_MAP[c] ?? c);
}

/**
 * 轴刻度：万 / 亿 缩写。
 * 六位数刻度（如 1200000）会把绘图区左右挤窄、标签互相压住，缩写后一眼可扫。
 */
function formatAxis(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e8) return `${(value / 1e8).toFixed(1)}亿`;
  if (abs >= 1e4) return `${(value / 1e4).toFixed(abs >= 1e6 ? 0 : 1)}万`;
  return String(Math.round(value));
}

/** 柱标签：带 ¥ 与千分位，过万自动缩写，保证一行放得下 */
function formatLabel(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e8) return `¥${(value / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `¥${(value / 1e4).toFixed(abs >= 1e6 ? 1 : 2)}万`;
  return `¥${value.toLocaleString("zh-CN", {
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
 * 低于「最大单笔变动 × 8%」的柱不写标签。
 *
 * 全员挂标签时柱顶是一排长短不一的数字，最小的几根会和相邻柱的标签挤成一团，
 * 反而看不出哪根重要。它们的完整数值仍在 tooltip 里（轴触发，鼠标移到即读），
 * 所以不是「信息没了」，只是不再和图抢注意力。终点柱（净资产）恒显示。
 */
const LABEL_MIN_RATIO = 0.08;

/**
 * 由 distributions 构造柱序列。
 *
 * 柱几何是「底座 + 增量」两层堆叠，而不是「把累计值当普通柱高、从 0 画到累计值」：
 * 后者柱高表达的是**累计**、标签写的却是**增量**，两者对不上（最大的那根柱未必是
 * 对应大类里最大的那个），首个大类还会被压成一根贴地的矮柱。改成真正的瀑布后，
 * 每根柱只画自己那一份增量、悬在自己的累计高度上——柱高 = 标签 = 该大类的金额，
 * 一眼比得出大小，「小柱贴地」也随之消失（它本来就该矮）。
 *
 *   · 正增：base = 变化前累计，柱从 base 长到 base + value
 *   · 负增（负债）：base = 变化后累计（较低的那个），柱从 base 长回变化前，
 *     于是在视觉上是「从高处掉下来」的一段，而不是一根从 0 起的新柱
 */
export function buildWaterfallBars(
  distributions: DistributionsData
): WaterfallBar[] {
  const categories = distributions.category_distribution ?? [];
  const totalLiab = distributions.total_liabilities ?? 0;
  const changes = [
    ...categories.map(c => ({ name: c.name, value: c.value })),
    ...(totalLiab > 0 ? [{ name: "负债", value: -totalLiab }] : [])
  ];

  const bars: WaterfallBar[] = [];
  let running = 0;
  for (const c of changes) {
    const before = running;
    running += c.value;
    bars.push({
      name: c.name,
      base: Math.min(before, running),
      delta: Math.abs(c.value),
      change: c.value,
      cumulative: running,
      isEndpoint: false
    });
  }
  // 终点柱：净资产。它是「各大类累加后扣掉负债」的落点，与标题旁的口径 ⓘ 一致
  const end = distributions.net_worth ?? running;
  bars.push({
    name: "净资产",
    base: Math.min(0, end),
    delta: Math.abs(end),
    change: end,
    cumulative: end,
    isEndpoint: true
  });
  return bars;
}

/** distributions 里既没有大类也没有负债 ⇒ 无可画，返回 null 让调用方跳过 setOption */
export function hasWaterfallData(distributions: DistributionsData): boolean {
  const hasCategories = (distributions.category_distribution ?? []).length > 0;
  return hasCategories || (distributions.total_liabilities ?? 0) > 0;
}

function barColor(b: WaterfallBar, c: WaterfallColors): string {
  if (b.isEndpoint) return c.info;
  if (b.change > 0) return c.rise;
  if (b.change < 0) return c.fall;
  return c.neutral;
}

function inkColor(b: WaterfallBar): string {
  if (b.isEndpoint) return INK_PRIMARY;
  if (b.change > 0) return INK_RISE;
  if (b.change < 0) return INK_FALL;
  return INK_NEUTRAL;
}

/**
 * 构造 echarts option。**不返回 `EChartsOption` 类型**：`@/plugins/echarts` 的
 * 类型定义对 `itemStyle.color` / `label.formatter` 这类回调形参极窄，
 * 显式标注反而要写一堆 `as any`，与本仓「禁 any」的约束相悖。
 * 交给调用方的 `setOption` 自行做类型收窄。
 */
export function buildWaterfallOption(
  bars: WaterfallBar[],
  colors: WaterfallColors
) {
  // Y 轴下限必须把 0 与所有柱的最低点都圈进来：截断的柱状图会夸大差距
  const axisMin = Math.min(0, ...bars.map(b => b.base + b.delta));
  const maxAbsChange = Math.max(0, ...bars.map(b => Math.abs(b.change)));

  return {
    backgroundColor: "transparent",
    animationDuration: 420,
    // `as const`：不写它，这里的字符串字面量会被推断成 `string`，
    // 而 echarts 的 `AnimationEasing` 是字面量联合类型 ⇒ setOption 处报 TS2344。
    // 同理适用于下面 `axisPointer.type` 与各 `type: "bar"`。
    animationEasing: "cubicOut" as const,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" as const },
      formatter: (params: TooltipParam) => {
        const list = Array.isArray(params) ? params : [params];
        const bar = bars[list[0]?.dataIndex ?? -1];
        if (!bar) return "";
        const rows = bar.isEndpoint
          ? [["累计净资产", formatExact(bar.cumulative), INK_PRIMARY]]
          : [
              ["本项金额", formatExact(bar.change), inkColor(bar)],
              ["累计至本项", formatExact(bar.cumulative), INK_PRIMARY]
            ];
        const body = rows
          .map(
            ([label, value, color]) =>
              `<div style="display:flex;gap:16px;justify-content:space-between"><span>${label}</span>` +
              `<span style="font-variant-numeric:tabular-nums;color:${color}">${value}</span></div>`
          )
          .join("");
        return `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(bar.name)}</div>${body}`;
      }
    },
    grid: { left: 8, right: 12, top: 30, bottom: 4, containLabel: true },
    xAxis: {
      type: "category" as const,
      data: bars.map(b => b.name),
      axisLabel: {
        // 水平直排：类目名多为 2~6 个汉字，斜排 30° 既难认又把绘图区底部吃掉
        // 近 40px。窄容器放不下时由 hideOverlap 隐藏重叠项，而不是压成斜排。
        interval: 0,
        rotate: 0,
        hideOverlap: true,
        margin: 10,
        fontSize: 11,
        color: colors.axis
      },
      axisLine: { lineStyle: { color: colors.border } },
      axisTick: { show: false }
    },
    yAxis: {
      type: "value" as const,
      min: axisMin,
      splitNumber: 4,
      splitLine: { lineStyle: { color: colors.border } },
      axisLabel: {
        color: colors.axis,
        fontSize: 11,
        formatter: (v: number) => formatAxis(v)
      }
    },
    series: [
      {
        // 基座层：只负责把柱子垫到它该在的高度上，本身透明、不可点、不进 tooltip
        name: "基座",
        type: "bar" as const,
        stack: "waterfall",
        barMaxWidth: 40,
        silent: true,
        itemStyle: { color: "transparent" },
        emphasis: { disabled: true },
        tooltip: { show: false },
        data: bars.map(b => b.base)
      },
      {
        name: "资产大类",
        type: "bar" as const,
        stack: "waterfall",
        barMaxWidth: 40,
        // 极小金额仍留一丝可见高度，否则该柱完全消失、看不出「有这一项」
        barMinHeight: 2,
        data: bars.map(b => ({
          value: b.delta,
          itemStyle: { color: barColor(b, colors), borderRadius: 4 }
        })),
        label: {
          show: true,
          position: "top" as const,
          distance: 6,
          fontSize: 11,
          color: colors.textSecondary,
          formatter: (params: BarParam) => {
            const b = bars[params.dataIndex];
            if (!b || b.change === 0) return "";
            const bigEnough =
              b.isEndpoint ||
              (maxAbsChange > 0 &&
                Math.abs(b.change) >= maxAbsChange * LABEL_MIN_RATIO);
            if (!bigEnough) return "";
            const sign = b.isEndpoint || b.change > 0 ? "" : "-";
            return sign + formatLabel(b.change);
          }
        }
      }
    ]
  };
}
