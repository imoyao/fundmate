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
  /**
   * 极小值柱标注条的底色（`--bg-card`）。
   *
   * 标注条是**压在绘图区上**的一块文字，背后可能是网格线或相邻柱体的边缘；
   * 给它垫一层卡片底色，它才不会看起来像「浮在柱子上的脏字」。
   * 同样必须是解析值：canvas 不认 `var(--x)`（见上面 `riseInk` 那段）。
   */
  surface: string;
}

/**
 * 绘图区的实际尺寸（px），由宿主从容器 DOM 读出后传入。
 *
 * 为什么几何要由外面喂：本模块是纯计算，不读 DOM；而「柱高多少像素」「标注条放不放得下」
 * 这类判定**只能按像素**做（5px 在 376 万与 1 亿两种量级下含义完全一样，占总量的比例
 * 却差 27 倍）。宿主把 `el.clientHeight` 递进来，几何就在本模块内一次算清。
 *
 * **只收高度，不收宽度**：宽度随容器变，但 `chart.resize()` 只重排、不会重跑本模块——
 * 任何「按宽度算出来」的结论在窗口缩放后都会失真。标注条被刻意做成两行窄条
 * （宽 ≈ 46px，窄断点下类目带宽 ≈ 37px，相邻两根再靠行错位错开），因此不需要宽度信息。
 */
export interface WaterfallLayout {
  /** 图表容器高度（px）。取不到时按锁高 280 兜底 */
  height: number;
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

/* ────────────────────────────────────────────────────────────────────────────
 * 极小值柱的引线标注
 *
 * 要解决的问题：「保险 5.05 万」在 376 万量级下柱高只有约 3px，比 `barMinHeight`
 * 高不到哪去，视觉上就是一条粗虚线——用户既认不出是哪一类，也读不出值。
 *
 * **柱高一个像素都不动**：柱高严格等于金额（那是这张图的契约）。当柱高不足以承载
 * 信息时，只能**在柱子上叠加一层标注**去说「这是谁 + 多少」，而不是把柱子拔高。
 * 拔高 3px 的柱子会让它看起来和 20 万的柱子一样高，那是改数据。
 *
 * 叠加层分三件：标注条（label，两行：名称 / 金额）+ 引线（markLine，1px）+ 卡片底色
 * 垫底。三者全部 `silent`、不进 tooltip（tooltip 仍由轴触发，值仍是完整精度）。
 * ──────────────────────────────────────────────────────────────────────────── */

/**
 * 判定为「极小值柱」的柱高上限（px）。**按像素判，不按占总量的比例判**：
 *
 * 比例阈值在不同量级下说的不是同一件事 —— 5px 在 376 万和 1 亿两张图里都是「一条虚线」，
 * 而它占总量的比例会差 27 倍，用比例当阈值必然一边漏一边误伤。
 *
 * 为什么是 12px（三条都指向同一个量级）：
 *   · 柱体 `borderRadius: 4` 吃掉上下各 4px，柱高 ≤ 12px 时几乎整根都是圆角，
 *     没有直边可比长短，长度信息本就失效；
 *   · 柱标签字号 11px —— 柱子比一行字还矮时，标签会比柱子显眼得多，
 *     「谁在标注谁」读不出来；
 *   · 引线 1px，柱高再矮下去两者宽度接近，会被读成同一根断掉的虚线。
 *
 * **边界（什么情况会漏）**：
 *   · 12px 以上、但仍够不上普通标签（`LABEL_MIN_RATIO`）的柱依旧不写标签 —— 那是原有
 *     行为，不在本次范围里；本层只接住「连柱高都读不出来」的那一档。这条空隙只在
 *     「某一步独大、几乎顶满轴高」时出现（阈值 8% × 最大单步 ≈ 轴高的 8%，而 12px
 *     约占轴高 5.4%，两个区间只在最大单步接近轴高时重叠），故意不为此抬高阈值；
 *   · 容器高度取不到时按锁高 280 兜底，阈值照旧成立（本卡高度是锁死的，不随断点变）；
 *   · `barMinHeight: 2` 会让 < 2px 的柱子实际画成 2px，所以极低端的像素只是估值 ——
 *     但 2px 远在阈值之下，不影响判定方向；
 *   · 终点柱（净资产）永不改挂标注：它恒有普通标签，且它是结论、不该被降级成注解；
 *   · 金额为 0 的档位不看（`change === 0`），它今天就是不可见的。
 */
export const TINY_BAR_PX = 12;

/** 网格内边距（px）。与 `grid` 选项共用同一组常量 —— 分开写会让像素换算与实际布局脱拍 */
const GRID_INSET = { left: 8, right: 12, top: 30, bottom: 4 } as const;

/** x 轴类目文字吃掉的高度（fontSize 11 + margin 10，实测约 22px） */
const X_AXIS_BAND_PX = 22;

/** 容器高度取不到时的兜底：与宿主 `.overview-card__body` 的锁高一致 */
const FALLBACK_CONTAINER_HEIGHT = 280;

/**
 * 标注条的排版尺寸（px）。**必须与下面 label 里用的值同源**——
 * 引线终点是按 `CHIP_HEIGHT` 算的，改了字号却不改这里，引线会插进字里。
 */
const CHIP_FONT_PX = 10;
const CHIP_LINE_HEIGHT = 11;
const CHIP_PADDING_Y = 2;
const CHIP_PADDING_X = 3;
const CHIP_HEIGHT_PX = CHIP_LINE_HEIGHT * 2 + CHIP_PADDING_Y * 2; // 26

/** 名称截断长度：4 个汉字 + 金额 ≈ 46px，与窄断点的类目带宽同量级，见 `WaterfallLayout` 注释 */
const CHIP_NAME_MAX_CHARS = 4;

/** 引线与柱顶之间留的空隙：贴上去会和柱顶的圆角、连接线糊成一团 */
const LEADER_GAP_PX = 2;

/** 第一行标注条离柱顶的距离（含引线长度）；第二行再往下压一整个标注条 */
const CALLOUT_ROW0_DISTANCE = 10;
const CALLOUT_ROW_OFFSET = CHIP_HEIGHT_PX + 6;

interface TinyCallout {
  index: number;
  /** label.distance：标注条底边到柱顶的像素距离 */
  distance: number;
  /** 引线两端的数据坐标 y；放不下（顶部空间不足）时为 null，只留标注条 */
  leader: [number, number] | null;
  /** rich 文本（两行） */
  text: string;
  /** 金额那一行的字色：与柱自身语义一致 */
  ink: string;
}

/**
 * 取一个「整数档」的刻度步长（1 / 2 / 2.5 / 5 × 10ⁿ）。
 *
 * 轴上限自己算而不是交给 echarts 自动，是为了让**像素换算可复现**：自动上限会随着
 * 「多一分钱」换档，阈值随之忽大忽小，同一张图两次刷新可能一次标注一次不标注。
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

/** 名称截断：超出 4 字按「前 3 字 + …」，标注条宽度才不会越过类目带宽 */
function truncateChipName(name: string): string {
  const chars = Array.from(name);
  return chars.length <= CHIP_NAME_MAX_CHARS
    ? name
    : `${chars.slice(0, CHIP_NAME_MAX_CHARS - 1).join("")}…`;
}

/**
 * 标注条里的金额：不足 1 万的省掉角分（`¥5,000` 比 `¥5,000.00` 窄三成），
 * 1 万以上沿用柱标签同一套万 / 亿缩写。完整精度仍在 tooltip 里。
 */
function formatChipValue(value: number): string {
  return Math.abs(value) < 1e4
    ? formatAmount(value, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
      })
    : formatLabel(value);
}

/** rich 文本的语法字符要剔除，否则名称里的 `{` / `|` 会把标注条解析成乱码 */
function safeRichText(raw: string): string {
  return raw.replace(/[{}|\r\n]/g, "");
}

function chipText(bar: WaterfallBar): string {
  const name = safeRichText(truncateChipName(bar.name));
  const value = safeRichText(formatChipValue(bar.change));
  return `{n|${name}}\n{v|${value}}`;
}

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
  colors: WaterfallColors,
  layout?: WaterfallLayout
) {
  // Y 轴下限必须把 0 与所有柱的**最低点**都圈进来：截断的柱状图会夸大差距。
  // 最低点取 `base`（柱底）而不是 `base + delta`（柱顶）：负增柱的柱底才是它
  // 落到的最低处，用柱顶算等于只看上半截 —— 净值转负时柱子会被轴裁掉一截，
  // 而且画面上看不出来（图还画得出来，只是矮了）。
  const dataMin = Math.min(0, ...bars.map(b => b.base));
  const dataMax = Math.max(0, ...bars.map(b => b.base + b.delta));
  const axisMin = dataMin;
  // 轴上限**自己算**，不再交给 echarts 自动取：极小值判定按像素高度做，而自动上限
  // 会随数据抖动换档（多一分钱就可能换一档），同一份数据两次刷新可能一次标注、
  // 一次不标注。这里用「整数档步长 × 4~5 段」把它钉死，像素换算才可复现。
  const step = niceStep((dataMax - dataMin) / 4);
  const axisMax = Math.max(
    axisMin + step,
    axisMin + Math.ceil((dataMax - axisMin) / step) * step
  );
  /** 绘图区高度：容器高 − 上下内边距 − x 轴类目文字那一条 */
  const plotHeight = Math.max(
    80,
    (layout && layout.height > 0 ? layout.height : FALLBACK_CONTAINER_HEIGHT) -
      GRID_INSET.top -
      GRID_INSET.bottom -
      X_AXIS_BAND_PX
  );
  /** 1px 代表多少金额 —— 极小值判定的唯一单位换算 */
  const unitsPerPx = (axisMax - axisMin) / plotHeight;
  /**
   * `LABEL_MIN_RATIO` 的母体：**单笔变动**里的最大者。
   *
   * ⚠️ 必须排除终点柱（净资产）。它的 `change` 是全部步骤的**合计**、不是一次变动，
   * 拿它当母体会把阈值抬到「8% × 净资产」，中小档位被整批误判成「不值得标」：
   * 实测 376 万净资产 + 30 万现金档 ⇒ 阈值 30.004 万，现金差 40 元落榜，
   * 而 20 万的负债档因为矮于 `TINY_BAR_PX` 反而拿到了标注条 —— 同一张图上
   * 「30 万没数字、20 万有数字」，比不标更费解。
   */
  const maxAbsChange = Math.max(
    0,
    ...bars.filter(b => !b.isEndpoint).map(b => Math.abs(b.change))
  );

  /**
   * 挑出「柱高读不出来、又没有普通标签」的那几档，改挂引线标注。
   *
   * 与普通标签**互斥**（`plainLabel` 一票否决）：两者都画会在同一根柱顶上叠两个数字。
   * 相邻的两根交替向上错一行（`CALLOUT_ROW_OFFSET`），因为标注条比类目带宽略宽，
   * 同一行并排会互相压字；不相邻的回到第一行，避免整排标注条被无谓地抬高。
   */
  const callouts = new Map<number, TinyCallout>();
  {
    let previous = -2; // 哨兵：保证第 0 根一定落在第一行
    let row = 0;
    bars.forEach((b, i) => {
      const heightPx = b.delta / unitsPerPx;
      const plainLabel =
        b.isEndpoint ||
        (maxAbsChange > 0 &&
          Math.abs(b.change) >= maxAbsChange * LABEL_MIN_RATIO);
      if (
        b.isEndpoint ||
        b.change === 0 ||
        plainLabel ||
        heightPx >= TINY_BAR_PX
      ) {
        return;
      }
      row = i === previous + 1 ? 1 - row : 0;
      previous = i;

      const top = b.base + b.delta;
      // 柱上方的可用空间 = 绘图区里柱顶以上的高度 + `grid.top` 那段留白
      // （标签画得进留白里，不会被绘图区裁掉）。顶部附近的柱靠压缩引线长度让位，
      // 而不是把标注条推到画布外。
      const roomPx = (axisMax - top) / unitsPerPx + GRID_INSET.top;
      const wanted = CALLOUT_ROW0_DISTANCE + row * CALLOUT_ROW_OFFSET;
      const distance = Math.max(
        LEADER_GAP_PX + 2,
        Math.min(wanted, roomPx - CHIP_HEIGHT_PX)
      );
      const leaderLength = distance - LEADER_GAP_PX;
      callouts.set(i, {
        index: i,
        distance,
        // 短于 3px 的引线不画：它画出来只是柱顶多一个点，不如让标注条自己说
        leader:
          leaderLength >= 3
            ? [
                top + LEADER_GAP_PX * unitsPerPx,
                top + (distance - 1) * unitsPerPx
              ]
            : null,
        text: chipText(b),
        ink: inkColor(b, colors)
      });
    });
  }

  const leaderSegments = Array.from(callouts.values())
    .filter(c => c.leader !== null)
    .map(c => {
      const [from, to] = c.leader as [number, number];
      return [{ coord: [c.index, from] }, { coord: [c.index, to] }];
    });

  /**
   * 相邻柱之间的连接线：从上一根柱的收尾水位，横着连到下一根柱的起点。
   *
   * 没有它，每根柱只是「悬在自己高度上的一根柱子」，读者看不出它们是同一笔钱
   * 一笔笔累加出来的（观感上像散点）。标准瀑布图的「台阶」就是这条线。
   * `cumulative` 正是上一根柱收尾的水位，也等于下一根柱的起点之一。
   */
  const connectors = bars
    .slice(0, -1)
    .map((b, i) => [
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
    grid: {
      left: GRID_INSET.left,
      right: GRID_INSET.right,
      top: GRID_INSET.top,
      bottom: GRID_INSET.bottom,
      containLabel: true
    },
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
      max: axisMax,
      // 刻度步长显式给定：上限是我们算的，若再让 echarts 自选刻度，会出现
      // 「最后一格落在 max 之外」的缝隙（4 段装 5 段的数据）。步长与上限同源就不会走样。
      interval: step,
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
        data: bars.map((b, i) => {
          const callout = callouts.get(i);
          return {
            value: b.delta,
            itemStyle: { color: barColor(b, colors), borderRadius: 4 },
            // 标签字色按**柱自己的语义**取（终点=主文字、涨=rise-ink、跌=fall-ink），
            // 逐条覆盖而不是在 series.label 里写死一个灰：文件头那套 -ink 口径
            // 与 design.md「柱体用 rise/fall 填充、柱上文字用 -ink 级」是同一件事，
            // 写死灰等于把这条约定留在了注释里。
            //
            // 极小值柱的标签升级成「两行标注条 + 引线」（见文件内 TINY_BAR_PX 那段）：
            // 名称走 --text-tertiary-ink（它是索引，不是数字），金额走柱自己的 -ink；
            // 垫一层卡片底色，压在网格线上也不脏。`distance` 由几何算出，不是写死的 6。
            label: callout
              ? {
                  distance: callout.distance,
                  backgroundColor: colors.surface,
                  padding: [CHIP_PADDING_Y, CHIP_PADDING_X],
                  borderRadius: 3,
                  align: "center" as const,
                  fontSize: CHIP_FONT_PX,
                  lineHeight: CHIP_LINE_HEIGHT,
                  color: colors.axis,
                  rich: {
                    n: {
                      fontSize: CHIP_FONT_PX,
                      lineHeight: CHIP_LINE_HEIGHT,
                      color: colors.axis,
                      align: "center" as const
                    },
                    v: {
                      fontSize: CHIP_FONT_PX,
                      lineHeight: CHIP_LINE_HEIGHT,
                      color: callout.ink,
                      align: "center" as const,
                      fontWeight: 600
                    }
                  }
                }
              : { color: inkColor(b, colors) }
          };
        }),
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
            // 极小值柱走「两行标注条」，普通柱走单行金额。两者互斥由 callouts 保证，
            // 这里再按它分流一次：同一根柱顶不会出现两个数字。
            const callout = callouts.get(params.dataIndex);
            if (callout) return callout.text;
            const bigEnough =
              b.isEndpoint ||
              (maxAbsChange > 0 &&
                Math.abs(b.change) >= maxAbsChange * LABEL_MIN_RATIO);
            if (!bigEnough) return "";
            // 负号由 formatLabel 统一产生（且在 ¥ 之前），这里不再拼第二遍
            return formatLabel(b.change);
          }
        }
      },
      // 引线层：**只承载 markLine**，没有任何数据、不画线、不进 tooltip。
      // 单独一条 series 是因为一个 series 只能挂一条 markLine，而
      // 「资产大类」上那条已经被连接线占用了（两者的线型 / 透明度也不同）。
      ...(leaderSegments.length > 0
        ? [
            {
              name: "极小值引线",
              type: "line" as const,
              // 全 null 而不是空数组：空数组会让部分 echarts 版本跳过该 series 的
              // 布局，markLine 跟着不画（这条 series 存在的唯一理由就是它的 markLine）
              data: bars.map(() => null),
              showSymbol: false,
              silent: true,
              tooltip: { show: false },
              animation: false,
              emphasis: { disabled: true },
              markLine: {
                silent: true,
                symbol: "none" as const,
                animation: false,
                label: { show: false },
                emphasis: { disabled: true },
                lineStyle: {
                  // 与连接线同色（--text-tertiary 的解析值），但更淡、且是实线：
                  // 虚线在这里会被读成「又一条台阶」，实线才像一根引出的小钉。
                  color: colors.connector,
                  width: 1,
                  opacity: 0.45,
                  type: "solid" as const
                },
                data: leaderSegments
              }
            }
          ]
        : [])
    ]
  };
}
