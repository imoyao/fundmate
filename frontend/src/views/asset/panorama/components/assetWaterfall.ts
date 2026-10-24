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
  /** 轴标签色。design.md：凡 `color:` 用途一律走 --text-tertiary-ink */
  axis: string;
  border: string;
  /**
   * 瀑布连接线（相邻柱之间那条虚线）的颜色。
   * 取 --text-tertiary（colors.css 的「辅助描边 / 图形」级）：--border-* 两档
   * 在白卡上只有 ~5~11% 明度差，1px 虚线实际看不见，而「柱子是一笔笔累加来的」
   * 正是它存在的**唯一**理由。
   */
  connector: string;
  /**
   * 柱标签 / tooltip 的文字色，`-ink` 级（design.md：柱体用 rise/fall 填充，
   * 柱上文字用 -ink 才达 AA）。
   *
   * ⚠️ **必须是已解析的颜色值，不能传 `var(--x)`**：echarts 的标签画在 canvas 上，
   * canvas 的 `fillStyle` 不认 CSS 变量——赋值会被静默忽略、退回上一次的 fillStyle，
   * 症状是「标签颜色时灰时绿、与柱无关」（本模块曾因此把标签写死成灰色）。
   * tooltip 走 HTML 才吃 CSS 变量；这里统一用解析值，两条出口颜色必然一致。
   */
  riseInk: string;
  fallInk: string;
  neutralInk: string;
  primaryInk: string;
}

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

/**
 * 柱标签 / tooltip：带 ¥ 与千分位，过万自动缩写，保证一行放得下。
 *
 * **负号必须在 ¥ 之前**（design.md「数字格式规范」：负数写作 `-¥1,234.56`）。
 * 早先的实现是「formatter 先拼 `-`，再让本函数拼 `¥`」两条路各拼一次，
 * 而本函数内部又用 `value` 而不是 `abs` 去格式化 ⇒ `¥-176.0万`（符号夹在 ¥ 后）、
 * 极端时甚至 `-¥-176.0万`（双负号）。现在符号只在本函数产生一次，其余一律取 abs。
 */
function formatAmount(value: number, opts: NumericFormat): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  return sign + `¥${abs.toLocaleString("zh-CN", opts)}`;
}

type NumericFormat = {
  minimumFractionDigits: number;
  maximumFractionDigits: number;
};

function formatLabel(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}¥${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${sign}¥${(abs / 1e4).toFixed(abs >= 1e6 ? 1 : 2)}万`;
  return formatAmount(value, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

/** tooltip：完整精度，不缩写（用户是来读确切数字的） */
function formatExact(value: number): string {
  return formatAmount(value, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
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

/**
 * 柱标签 / tooltip 的字色：与 `barColor` 同一套语义，取 `-ink` 级。
 * 终点柱（净资产）用主文字色——它是结论，不该被涨跌色再说一遍。
 */
function inkColor(b: WaterfallBar, c: WaterfallColors): string {
  if (b.isEndpoint) return c.primaryInk;
  if (b.change > 0) return c.riseInk;
  if (b.change < 0) return c.fallInk;
  return c.neutralInk;
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
  // Y 轴下限必须把 0 与所有柱的**最低点**都圈进来：截断的柱状图会夸大差距。
  // 最低点取 `base`（柱底）而不是 `base + delta`（柱顶）：负增柱的柱底才是它
  // 落到的最低处，用柱顶算等于只看上半截 —— 净值转负时柱子会被轴裁掉一截，
  // 而且画面上看不出来（图还画得出来，只是矮了）。
  const axisMin = Math.min(0, ...bars.map(b => b.base));
  const maxAbsChange = Math.max(0, ...bars.map(b => Math.abs(b.change)));

  /**
   * 相邻柱之间的连接线：从上一根柱的收尾水位，横着连到下一根柱的起点。
   *
   * 没有它，每根柱只是「悬在自己高度上的一根柱子」，读者看不出它们是同一笔钱
   * 一笔笔累加出来的（观感上像散点）。标准瀑布图的「台阶」就是这条线。
   * `cumulative` 正是上一根柱收尾的水位，也等于下一根柱的起点之一。
   */
  const connectors = bars.slice(0, -1).map((b, i) => [
    { coord: [i, b.cumulative] },
    { coord: [i + 1, b.cumulative] }
  ]);

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
          ? [["累计净资产", formatExact(bar.cumulative), colors.primaryInk]]
          : [
              ["本项金额", formatExact(bar.change), inkColor(bar, colors)],
              ["累计至本项", formatExact(bar.cumulative), colors.primaryInk]
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
        // 0 轴：轴下限一旦被拉到负数（净值 / 中途累计转负），x 轴那条线就不再是
        // 0 了，柱子的「零位」在图上没有任何标记。此时补一条实线把 0 画出来；
        // 全正时轴下限本来就是 0（x 轴线即零轴），再画一遍是多余的噪声。
        ...(axisMin < 0
          ? {
              markLine: {
                silent: true,
                symbol: "none" as const,
                animation: false,
                label: { show: false },
                emphasis: { disabled: true },
                lineStyle: {
                  color: colors.axis,
                  width: 1,
                  opacity: 0.45,
                  type: "solid" as const
                },
                data: [{ yAxis: 0 }]
              }
            }
          : {}),
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
          itemStyle: { color: barColor(b, colors), borderRadius: 4 },
          // 标签字色按**柱自己的语义**取（终点=主文字、涨=rise-ink、跌=fall-ink），
          // 逐条覆盖而不是在 series.label 里写死一个灰：文件头那套 -ink 口径
          // 与 design.md「柱体用 rise/fall 填充、柱上文字用 -ink 级」是同一件事，
          // 写死灰等于把这条约定留在了注释里。
          label: { color: inkColor(b, colors) }
        })),
        markLine: {
          // 连接线：不进 tooltip、不响应鼠标、不参与图例
          silent: true,
          symbol: "none" as const,
          animation: false,
          label: { show: false },
          emphasis: { disabled: true },
          lineStyle: {
            color: colors.connector,
            width: 1,
            // 虚线压到 60% 不透明度：它要「看得见但不抢柱子的注意力」，
            // 与网格线同族的轻，只是深一档。
            opacity: 0.6,
            type: [3, 3] as [number, number]
          },
          data: connectors
        },
        label: {
          show: true,
          position: "top" as const,
          distance: 6,
          fontSize: 11,
          formatter: (params: BarParam) => {
            const b = bars[params.dataIndex];
            if (!b || b.change === 0) return "";
            const bigEnough =
              b.isEndpoint ||
              (maxAbsChange > 0 &&
                Math.abs(b.change) >= maxAbsChange * LABEL_MIN_RATIO);
            if (!bigEnough) return "";
            // 负号由 formatLabel 统一产生（且在 ¥ 之前），这里不再拼第二遍
            return formatLabel(b.change);
          }
        }
      }
    ]
  };
}
