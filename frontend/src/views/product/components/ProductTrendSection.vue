<script setup lang="ts">
import { computed, ref, watch } from "vue";
import VChart from "vue-echarts";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import {
  TREND_VIEW_OPTIONS,
  effectiveUseCandle,
  overlayAvailable,
  showViewToggle,
  showVolumeSeries,
  type TrendView
} from "./trendViewMetrics";
import {
  formatReturnPercent,
  toCumulativeReturn,
  toReturnPct,
  trendBasisOptions,
  type TrendBasis
} from "./trendBasisMetrics";
import {
  getProductTrend,
  getTradeTimeline,
  type ProductTrendResult,
  type TradeTimelineResult,
  type TrendRange
} from "@/api/products";
import ProductProfitPanel from "./ProductProfitPanel.vue";
import {
  SELL_SIZE_RATIO,
  UNIFIED_SIZE,
  clearingLabel,
  clearingMarks,
  markerMaxSize,
  markerSize,
  maxAmountOf
} from "./trendMarkerMetrics";
import {
  CHART_FALLBACKS,
  CHART_TOKENS,
  getCssVar,
  useThemeTick
} from "@/composables/echarts/theme";
import { formatPrice, priceAxisLabelFormatter } from "@/utils/pricePrecision";

/**
 * 详情页「走势」区块（#1967 · 设计 §5 B 区块）。
 *
 * 口径与红线：
 * - 区间 `1M/3M/6M/1Y/3Y/5Y`，**默认 3M**（设计 §12 ⑤；3Y/5Y 为 2026-10-17 长区间
 *   补充档——短期收益不代表长期收益）；历史不够长时由 `available_days`
 *   判断并提示收敛，不画一条只有几天的曲线假装是 3M；
 * - **品类差异化**（#1969）：场内有 OHLCV → K 线 + 成交量 + MA5/10/20（口径未复权，
 *   与持仓成本可比）；场外基金只有净值 → 净值线（#2171 起为**累计净值**，
 *   缺失回退单位净值，与业绩卡同源——单位净值遇分红除息跳空是假暴跌）；
 * - 图表颜色一律经 `getCssVar` 取**真实色值**：ECharts 不解析 `var(--x)`，给变量字符串
 *   等于给了一个无效色（旧版 splitLine 的写法就是这么错的，也会让网格看起来发黑发乱）；
 * - 线条**不平滑**：smooth 会画出实际不存在的峰谷，价格序列上属失真；
 * - **无数据就显示空态**，绝不用 mock 顶替（设计 G1 教训）；
 * - 脚注写明「数据日期 · 来源 · 口径」——来源是站点名，不是内部表名（#1969）；
 * - **品类无序列源时整卡不渲染**（#1967 后续）：后端对 manager / portfolio /
 *   无日线的 index 返回 `kind=''` + 空序列，此时渲染出的只有标题的卡片是纯噪声。
 *   走势区块已从最后一屏移回首屏（设计 §5 B 位），这条降级从「脚注」升级为
 *   「区块整体不渲染」（设计 §6 降级规则）。判据取后端 `kind` 而非在前端镜像
 *   一份「哪些品类没序列」的类型清单——后端 `product_trend._NO_SERIES_TYPES`
 *   是权威，前端不复制它。
 *
 * ## 买卖点 / 成本线叠加（#2171）
 *
 * - **叠加层只在折线视图**：买卖点（锚定当日净值 / 收盘价）与成本线（`avg_cost_yuan`）
 *   都与折线同轴可比。成本线**必须**取「元/份」那个字段——取总成本会让曲线被压平
 *   （见 `costSeriesData` 注释）；
 * - **场内提供「K线 / 折线」两个视图**（#2171 后续）：K 线是**未复权价格** + cross tooltip
 *   + 双 grid（量能副图），叠买卖点等于在同图上放第二套坐标语义，故**不往 K 线上硬叠**；
 *   场内要看买卖点就切折线视图（画**收盘价**，与持仓成本同口径），直接复用同一套叠加层与
 *   成本线口径，不新写坐标。三个视图判定（切换器是否可见 / 成交量副图 / 叠加层是否可用）
 *   收口在 `trendViewMetrics`（含单测）；
 * - 买卖点的复盘场景另有更合适的落点：资产复盘页的「调仓时间线」
 *   （`docs/features/asset-review.md` 组件 5，按周期列出每笔买卖 + 卖出的实现盈亏）；
 * - **取色避开 rise/fall**：买卖点不是涨跌语义，红绿会让「我买过」被误读成「涨了」。
 *   蓝（info）三角朝上=买入、橙（warning）三角朝下=卖出、中性灰虚线=成本线——
 *   形状主编码，色弱用户也能分辨；
 * - **低于当时成本线 → 空心**（P1）：当日均价 < 当日最后一笔之前的持仓均价。
 *   低吸 / 割肉一眼可辨，tooltip 附偏离度；首笔前无持仓不判（无参照不下结论）。
 *   不引入第三种颜色——那会和涨跌语义打架；
 * - **同日多笔聚合**为一个点（金额合计 + 笔数），tooltip 显示「N 笔合计」；
 * - **点大小 = 弱金额权重**（#2171 §4.2）：直径 6–16px，`min + (max−min)×√权重`（开方是
 *   刻意的：金额长尾，线性映射会让一笔大额买入把其余点全压成米粒）；权重按本侧当日聚合
 *   金额归一，**点数 > 20 自动压低上限**（不按周/月聚合——那会改变「哪天操作的」这个事实）；
 *   卖点上限再低一档；「统一大小」开关可关掉权重映射。公式与边界住在
 *   `trendMarkerMetrics`（含单测：开方映射 / 分母为 0 不产生 NaN —— NaN 会让 ECharts
 *   **默默不画这个点**，等于把交易记录藏了）；
 * - **成本线前向填充**：非交易日延续前值，首笔交易前为 null 不画，清仓日断在最后一笔；
 * - **「历轮」开关**（P1）：清仓后重建仓的用户可关掉旧轮次，只看最近一轮；
 * - **清仓轮次标记**（P2）：每轮结束（`closed`）在图上画一条**点线**竖线并编号
 *   （「第 N 轮清仓」；只有一轮时只写「清仓」——写「第 1 轮」是噪声）。编号按**全量**
 *   流水算、再按可见范围过滤，否则关掉「历轮」后标签会从第 1 轮重新开始、与实际不符；
 *   逻辑收口在 `trendMarkerMetrics.clearingMarks`（含单测）；
 * - **建仓期区间**（P1）：有流水时区间栏追加「建仓」档——首笔买入日至今，
 *   显式起始日走后端 `start` 参数（档位表达不了因人而异的长度）；
 * - **时间线不分区间**：后端一次返回全量重放结果，前端按当前区间过滤展示；
 * - 拉取失败 / 未持有 → 静默不渲染叠加层，主曲线不受影响（设计 §6）。
 *
 * ## 口径维度：净值 / 业绩（#2454）
 *
 * 走势图原来只有**净值/收盘价**一条线，答的是「现在多少钱」；用户要的**业绩走势**
 * 答的是「这段时间赚了多少」——后者从对前者的**纯派生**算出，不新开接口：
 *
 * - **基准 = 窗口首日**（不是成立以来）：用户问的是「这段」时间。成立以来收益是
 *   业绩卡的口径，同页不造第二个数字（#2171 决策）；
 * - 计算收口在 `trendBasisMetrics`（含单测）：首日恒 0、非有限值回落 0
 *   （ECharts 遇 NaN 会**默默跳过该点**，等于藏数据——`trendMarkerMetrics` 同款教训）；
 * - **业绩口径强制折线**：K 线画 OHLC 价格，没有「收益率 K 线」。合成判据是
 *   `basis === 'nav' && effectiveUseCandle(...)`——「实际在画什么」而不是
 *   「切换器选中什么」（#2453 纪律，选中值在切换器不渲染时没有语义）；
 * - 业绩口径下叠加层**重新锚定**到收益率空间（买卖点 y、成本线都按同一基准换算），
 *   tooltip 主行给 `收益率%（当日净值/成本 价格）`——只看 % 不知道当时多少钱；
 * - 画一条 **0% 基准线**：曲线本身从 0 出发，但没有这条线时「高于/低于基准」
 *  要靠眼估刻度；红涨绿跌沿用中国市场惯例（CHART_TOKENS.rise/fall）。
 *
 * ## 累计收益面板（P1，见 ProductProfitPanel.vue）
 *
 * 与叠加层共用同一次时间线请求（detail 层不重复取数）：累计已实现盈亏 +
 * 金额 / 收益率切换 + 紧凑统计条。曲线**全程展示不随区间缩放**——区间是看净值
 * 波动的窗口，不是看盈亏历史的窗口。
 */

const props = defineProps<{
  symbol: string;
  /** 品类：由 #1963 resolve 判定后回传，后端据此选收盘价 / 净值口径 */
  assetType?: string;
  /** 当前家庭是否持有该产品（详情页 resolve 回传）。仅持有时拉交易时间线——
      流水是私有数据，未持有用户发请求只会拿到空结构，还多一次往返（#2104 同款教训）。 */
  hasPosition?: boolean;
}>();

const RANGE_BASE_OPTIONS: { label: string; value: RangeValue }[] = [
  { label: "1月", value: "1M" },
  { label: "3月", value: "3M" },
  { label: "6月", value: "6M" },
  { label: "1年", value: "1Y" },
  // 长区间补充档（2026-10-17）：短期收益不代表长期收益，1 年看不出跨周期能力；
  // 历史不足时由 available_days 降级（前端收敛可用档），不编造曲线。
  { label: "3年", value: "3Y" },
  { label: "5年", value: "5Y" }
];

/**
 * 区间取值：固定档位 + 「建仓」（#2171 P1）。
 *
 * 建仓期 = 首笔买入日至今，长度因人而异（有人三年有人三天），档位表达不了——
 * 合并 research 纪要 §6 待办 #6（原计划单独一张卡）：落成走势卡的一个区间选项，
 * 复用同一张图与口径脚注，不为同一条曲线新开一张卡。仅在有流水时出现
 * （没买过就没有「建仓期」可言）。
 */
type RangeValue = TrendRange | "HOLDING";

const range = ref<RangeValue>("3M");
const loading = ref(false);
const failed = ref(false);
const trend = ref<ProductTrendResult | null>(null);

const themeTick = useThemeTick();

/** 品类无序列数据源（manager / portfolio / 无日线的 index）：后端 kind 返回空串。
    整卡不渲染，不在首屏顶一张空卡（设计 §6 降级规则；判据说明见组件头注释）。 */
const noSeries = computed(
  () => trend.value !== null && trend.value.kind === ""
);

/** hex → rgba：面积渐变需要具体色值（CSS 变量不能直接给 alpha） */
function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || "").trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

const hasData = computed(() => (trend.value?.values.length ?? 0) >= 2);

/**
 * 业绩序列（#2454）：区间累计收益率（%），基准 = 窗口首日。
 *
 * 与 `values` **等长按位对齐**（category 轴错位 = 整张图漂移）；非有限值已在
 * `trendBasisMetrics` 内回落 0——NaN 会被 ECharts 静默跳过，等于把数据藏了。
 */
const returnSeries = computed(() =>
  toCumulativeReturn(trend.value?.values ?? [])
);

/** 场内 = 有 OHLCV（具备画 K 线的能力）；场外基金 / 指数只有一条净值线（品类差异化） */
const isCandle = computed(() => (trend.value?.ohlc?.length ?? 0) >= 2);

/**
 * 场内视图（#2171 后续）：K 线 / 折线。
 *
 * 默认 K 线，既有观感不变。折线视图存在的唯一理由是**让买卖点与成本线能叠上来**——
 * 它们都是「元/份」「元/股」的日序列，只能与折线同轴（见 `trendViewMetrics` 头注释）。
 */
const candleView = ref<TrendView>("candle");

/**
 * 口径（#2454）：`nav` = 净值/收盘价绝对值；`return` = 区间累计收益率。
 *
 * 默认 `nav`（既有观感不变，K 线默认视图也不动）；「业绩」是用户明确要的第二个
 * 答案（「这段时间赚了多少」），与视图维度正交——口径决定 y 轴画什么，视图决定
 * 用什么画。场内外都给这个切换器：场外没有 K 线，但同样有「赚了多少」这个问题。
 */
const basis = ref<TrendBasis>("nav");

/** 口径切换器选项：第一项标签随品类变（场内「价格」/ 场外「净值」，#2171 后续） */
const basisOptions = computed(() => trendBasisOptions(isCandle.value));

/** 是否显示视图切换器：有 OHLCV 才谈得上「K 线」（场外给切换器是假选择）；
 **业绩口径下隐藏**——K 线没有收益率画法，留着一个点了没反应的选项是假可操作性。 */
const canToggleView = computed(
  () => showViewToggle(trend.value?.ohlc?.length ?? 0) && basis.value === "nav"
);

/**
 * 当前**真的**在画 K 线 = 具备能力 **且** 选的是 K 线视图 **且** 是净值口径。
 *
 * 走 `effectiveUseCandle`（含单测）而不是在组件里再拼一次
 * `isCandle && view === 'candle'`：拼漏、或改用「切换器选中值」代替「实际视图」，
 * 都会让叠加层判定与画面脱节（#2453）。
 *
 * `basis === 'nav'` 是第三道合取（#2454）：业绩口径没有 K 线这种画法
 * （K 线是 OHLC 价格），勾上「业绩」时无论视图选中值是什么，画的都是折线。
 */
const useCandle = computed(
  () =>
    basis.value === "nav" &&
    effectiveUseCandle(trend.value?.ohlc?.length ?? 0, candleView.value)
);

/**
 * 成交量副图：只随 K 线视图出现，且整段无量能时不占版面。
 * 两个条件各自成立（「有量能数据」≠「当前视图该显示量能」），故都交给 `trendViewMetrics`
 * 判定——把它们合成一个条件就会出现「切到折线后剩一个空网格」。
 */
const hasVolume = computed(() =>
  showVolumeSeries(
    candleView.value,
    (trend.value?.ohlc ?? []).some(o => (o.volume ?? 0) > 0)
  )
);

const candleCloses = computed(() =>
  (trend.value?.ohlc ?? []).map(o => o.close)
);

// ── 买卖点 / 成本线叠加（#2171）────────────────────────────────────
/**
 * 交易时间线（私有数据，仅持有时拉）。
 *
 * 未登录 / 无流水后端返回**同构空结构**（points/cost_line 为空数组），
 * 因此这里只判 `points.length`，不分支解析；拉取失败静默降级——
 * 叠加层是增量信息，主曲线不因为它挂掉（设计 §6 诚实降级）。
 */
const timeline = ref<TradeTimelineResult | null>(null);

/** 叠加层开关：默认开（「我买在了哪」是买方核心诉求），信息过载时可关 */
const showMarkers = ref(true);

/**
 * 「统一大小」开关（#2171 §4.2）：默认**关**（= 弱金额权重）。
 *
 * 两边都是合理需求：想看「大额买入在哪」的人要权重，只想看「我在哪买过」的人嫌点大点小
 * 让人分心。默认给权重（信息更多），想安静的人自己关。
 */
const unifiedSize = ref(false);

async function loadTimeline() {
  if (!props.symbol || props.hasPosition !== true) {
    timeline.value = null;
    return;
  }
  try {
    const res = await getTradeTimeline({ symbol: props.symbol });
    timeline.value = res.data;
  } catch {
    timeline.value = null;
  }
}

// 时间线不分区间（全量重放），symbol / 持有状态变化才重拉
watch(() => [props.symbol, props.hasPosition], loadTimeline, {
  immediate: true
});

/** 首笔交易日（建仓期区间的起点；无流水为 null） */
const firstTradeDate = computed(
  () => timeline.value?.summary.first_trade_date ?? null
);

/** 区间选项：有流水才追加「建仓」（没买过就没有建仓期可言） */
const rangeOptions = computed(() =>
  firstTradeDate.value
    ? [...RANGE_BASE_OPTIONS, { label: "建仓", value: "HOLDING" as RangeValue }]
    : RANGE_BASE_OPTIONS
);

/** 「历轮买卖」开关（#2171 P1）：默认开=显示全部轮次；关=只看最近一轮。
    清仓后重建仓的用户，旧轮次的点会让「我现在的成本线」难以认读。 */
const showHistoryRounds = ref(true);

/** 最近一轮的起点下标：最后一笔清仓（closed）的下一笔（无清仓则 0） */
const currentRoundStart = computed(() => {
  const pts = timeline.value?.points ?? [];
  for (let i = pts.length - 1; i >= 0; i--) {
    if (pts[i].closed) return i + 1;
  }
  return 0;
});

/** 是否存在历史轮次（决定「历轮」开关可不可见） */
const hasHistoryRounds = computed(() => currentRoundStart.value > 0);

/** 当前展示的交易点（历轮开关过滤后） */
const visiblePoints = computed(() => {
  const pts = timeline.value?.points ?? [];
  return showHistoryRounds.value ? pts : pts.slice(currentRoundStart.value);
});

/** 当前展示的成本线（与可见交易点同轮次；成本线在清仓后自然重启，
    按首个可见点的日期截断即可，不另造轮次概念） */
const visibleCostLine = computed(() => {
  const line = timeline.value?.cost_line ?? [];
  if (showHistoryRounds.value) return line;
  const pts = visiblePoints.value;
  if (!pts.length) return [];
  const from = pts[0].date;
  return line.filter(c => c.date >= from);
});

/**
 * 清仓轮次标记（#2171 P2）：在图上按轮次画竖线 + 编号。
 *
 * 编号必须按**全量**流水算（`clearingMarks` 的口径），再按当前可见范围过滤——否则关掉
 * 「历轮」后标签会从「第 1 轮清仓」重新开始，与真实轮次对不上。
 */
const clearingMarksList = computed(() => {
  const all = clearingMarks(timeline.value?.points ?? []);
  if (showHistoryRounds.value || !all.length) return all;
  const from = visiblePoints.value[0]?.date;
  return from ? all.filter(m => m.date >= from) : all;
});

/**
 * 日期 → 当前口径下的绘制值。
 *
 * 净值口径：买卖点画在**当日净值**位置（用户实际按净值成交，#2171 定稿）；
 * 业绩口径（#2454）：换算成**当日累计收益率**——y 轴已是 %，点还挂在净值上就悬空了。
 */
const plotValueByDate = computed(() => {
  const m = new Map<string, number>();
  const dates = trend.value?.dates ?? [];
  const values =
    basis.value === "return" ? returnSeries.value : (trend.value?.values ?? []);
  dates.forEach((d, i) => m.set(d, values[i]));
  return m;
});

/**
 * 买卖点 scatter 数据。
 *
 * **同日多笔按方向聚合**（金额合计、笔数计数）——不合并会两个点重叠成一个，
 * tooltip 也说不清「那天到底操作了几笔」。区间外的交易日（point.date 不在
 * trend.dates 里）直接丢弃：曲线没画到那天，点画上去是悬空的。
 *
 * **低于当时成本线的空心编码**（#2171 P1）：当日均价 < 当日最后一笔之前的持仓均价
 * → 空心三角。买在成本线下=低吸、卖在成本线下=割肉，都是买方要一眼看到的「这笔
 * 划不划算」（吸收自评估期砍掉的「越跌越买评分」）。首笔前无持仓（参照为 null）
 * 不判——没有参照就不下结论。
 */
const markerData = computed(() => {
  const nav = plotValueByDate.value;
  type MarkerMeta = {
    side: "buy" | "sell";
    date: string;
    y: number;
    amount: number;
    quantity: number;
    count: number;
    closed: boolean;
    confirm: string | null;
    account: string | null;
    /** 当日最后一笔之前的持仓均价（元/份）；无参照为 null */
    costRef: number | null;
  };
  const agg = new Map<string, MarkerMeta>();
  for (const p of visiblePoints.value) {
    const y = nav.get(p.date);
    if (y === undefined || !Number.isFinite(y)) continue;
    const key = `${p.side}@${p.date}`;
    const cur =
      agg.get(key) ??
      ({
        side: p.side,
        date: p.date,
        y,
        amount: 0,
        quantity: 0,
        count: 0,
        closed: false,
        confirm: p.confirm_date,
        account: p.account_name,
        costRef: null
      } as MarkerMeta);
    cur.amount += p.amount_yuan;
    cur.quantity += p.quantity;
    cur.count += 1;
    cur.closed = cur.closed || p.closed;
    // 取当日最后一笔的参照均价（聚合后与当日均价比较）
    if (p.cost_before_avg_yuan !== null) cur.costRef = p.cost_before_avg_yuan;
    agg.set(key, cur);
  }
  const decorate = (meta: MarkerMeta) => {
    const avgPrice = meta.quantity > 0 ? meta.amount / meta.quantity : null;
    const below =
      avgPrice !== null && meta.costRef !== null && avgPrice < meta.costRef;
    const deviation =
      avgPrice !== null && meta.costRef && meta.costRef > 0
        ? +(((avgPrice - meta.costRef) / meta.costRef) * 100).toFixed(2)
        : null;
    return {
      value: [meta.date, meta.y] as [string, number],
      ...meta,
      avgPrice,
      below,
      deviation
    };
  };
  const buy: ReturnType<typeof decorate>[] = [];
  const sell: ReturnType<typeof decorate>[] = [];
  for (const meta of agg.values()) {
    (meta.side === "buy" ? buy : sell).push(decorate(meta));
  }
  return { buy, sell };
});

/**
 * 买卖点直径（#2171 §4.2）。
 *
 * 权重按**本侧当日聚合金额**归一（分母 = 本侧最大金额）：两处同口径是必须的——
 * 分子用聚合额、分母用单笔最大值会让权重系统性 > 1，所有点顶到上限，「看金额大小」
 * 这个功能等于没有。买卖分侧各归一：买点 30 个不该把 2 个卖点跟着压小。
 * 卖点上限再乘一档（「小一号」）。公式与边界见 `trendMarkerMetrics`（含单测）。
 */
const sizedMarkers = computed(() => {
  const { buy, sell } = markerData.value;
  if (unifiedSize.value) {
    return {
      buy: buy.map(m => ({ ...m, symbolSize: UNIFIED_SIZE })),
      sell: sell.map(m => ({ ...m, symbolSize: UNIFIED_SIZE }))
    };
  }
  const buyMax = maxAmountOf(buy);
  const sellMax = maxAmountOf(sell);
  const buyCap = markerMaxSize(buy.length);
  const sellCap = markerMaxSize(sell.length) * SELL_SIZE_RATIO;
  return {
    buy: buy.map(m => ({
      ...m,
      symbolSize: markerSize(m.amount, buyMax, buyCap)
    })),
    sell: sell.map(m => ({
      ...m,
      symbolSize: markerSize(m.amount, sellMax, sellCap)
    }))
  };
});

/**
 * 成本线：`cost_line` 前向填充到区间每一天（非交易日延续前值；首笔交易前为 null 不画）。
 *
 * **取 `avg_cost_yuan`（元/份），不是 `cost_yuan`（总成本，元）** ——本图与净值共用一根
 * y 轴，只有「元/份」才可比。首版取了后者：真机一条 10,000 元的成本线把 y 轴拉到万元级，
 * 净值曲线（~1.x）被压成贴着 0 的直线，用户看到的正是「勾选买卖点后走势变成一条为 0 的
 * 直线」。#2171 反馈修正。
 */
const costSeriesData = computed(() => {
  const m = new Map(visibleCostLine.value.map(c => [c.date, c.avg_cost_yuan]));
  let last: number | null = null;
  return (trend.value?.dates ?? []).map(d => {
    if (m.has(d)) last = m.get(d) ?? null;
    return last;
  });
});

/**
 * 成本线的**绘制值**（#2454）：业绩口径下按同一基准（窗口首日）换算成收益率。
 *
 * 首笔交易前为 null 的位置**保持 null**——换算成 0 会画出一条假的 0% 成本线，
 * 用户会以为「最初的持仓成本就是基准」。
 */
const costPlotSeries = computed(() => {
  const raw = costSeriesData.value;
  if (basis.value !== "return") return raw;
  const base = trend.value?.values?.[0] ?? NaN;
  return raw.map(v => (v === null ? null : toReturnPct(v, base)));
});

/**
 * 叠加层在当前**实际**视图下是否可用（#2453 修复）。
 *
 * 传 `useCandle`（真的在画 K 线）而不是 `candleView`（切换器选中值）：场外基金没有
 * OHLCV，切换器根本不渲染，而选中值初值是 `'candle'` —— 按选中值判就成了「画的是
 * 折线、叠加层却不可用」，勾选框照常显示而买卖点一个都不画。判据与语义说明见
 * `trendViewMetrics.overlayAvailable`。
 */
const overlayUsable = computed(() => overlayAvailable(useCandle.value));

/**
 * 有交易点**且当前视图能叠**（决定开关可不可见）。
 *
 * 与 `markersActive` 的区别是不受开关自身影响——关掉开关后开关本身不能跟着消失
 * （否则用户再也开不回来）。视图不可叠时开关**必须隐藏**：显示一个点了没反应的
 * 勾选框是假可操作性，比不显示更糟。
 */
const hasMarkers = computed(
  () =>
    overlayUsable.value &&
    markerData.value.buy.length + markerData.value.sell.length > 0
);

/** 叠加层是否真的要画：开关开着 + 有交易点 + 当前视图能叠 */
const markersActive = computed(() => showMarkers.value && hasMarkers.value);

/**
 * 有交易点但被当前视图挡住（场内 K 线视图）：给一句明话。
 *
 * 开关隐藏了却什么都不说，用户只会以为「买卖点功能没了」。这句话同时也是
 * 「折线视图为什么存在」的答案——它的唯一理由就是让叠加层能叠上来。
 */
const tradesHiddenByView = computed(
  () =>
    !overlayUsable.value &&
    markerData.value.buy.length + markerData.value.sell.length > 0
);

/** 有流水（决定累计收益面板可不可见；含只有分红没有买卖的边界） */
const hasTrades = computed(() => {
  const s = timeline.value?.summary;
  if (!s) return false;
  return s.buy_count + s.sell_count + s.dividend_count > 0;
});

/**
 * 简单移动平均。
 *
 * 放在前端算：它是对已有收盘序列的**纯派生**（不跨表、不聚合明细），且切换区间时
 * 无需重新请求——后端只负责「数据从哪来、口径是什么」（数据策略约束针对的是跨表
 * 聚合，不是这种单序列滑窗）。
 */
function movingAverage(values: number[], window: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= window) sum -= values[i - window];
    out.push(i >= window - 1 ? +(sum / window).toFixed(3) : null);
  }
  return out;
}

/**
 * 蜡烛图数据。
 *
 * ECharts 的 `candlestick` 要求 `[open, close, low, high]` 这个**固定顺序**（不是
 * OHLC 顺序）——写错不会报错，只会画出一条形状诡异的图。
 *
 * 盘中价缺失时用收盘价兜底：ECharts 不接受 null，而「没有盘中数据」在图上表现为
 * 一根没有上下影线的横线，比整段图缺一根要诚实。
 */
const candleData = computed(() =>
  (trend.value?.ohlc ?? []).map(o => [
    o.open ?? o.close,
    o.close,
    o.low ?? o.close,
    o.high ?? o.close
  ])
);

/** 历史不足：实际跨度不到请求区间的一半 → 提示已收敛（长区间待 #1535 落库后放开） */
const spanNotice = computed(() => {
  const t = trend.value;
  if (!t || !hasData.value) return "";
  if (t.available_days >= t.requested_days * 0.5) return "";
  return `历史数据仅覆盖 ${t.available_days} 天，短于所选区间`;
});

const chartOption = computed(() => {
  void themeTick.value; // 主题切换时重算，让曲线重读 CSS 变量
  const dates = trend.value?.dates ?? [];
  const values = trend.value?.values ?? [];
  const rise = getCssVar(CHART_TOKENS.rise, CHART_FALLBACKS.rise);
  const fall = getCssVar(CHART_TOKENS.fall, CHART_FALLBACKS.fall);

  // 网格线取**真实色值**并用实线：
  // · ECharts 不解析 `var(--x)`，直接给变量字符串等于给了一个无效色（旧版就是）；
  // · 虚线在密集 K 线与影线之间会糊成一片，是「看着杂乱」的一半原因（#1969）。
  const splitLine = {
    lineStyle: {
      color: getCssVar(CHART_TOKENS.borderLight, CHART_FALLBACKS.borderLight)
    }
  };

  if (useCandle.value) {
    // 成交量副图：与 K 线共用 x 轴（放下面一格），整段无量能时不渲染这一格
    const volumeSeries = hasVolume.value
      ? [
          {
            name: "成交量",
            type: "bar",
            xAxisIndex: 1,
            yAxisIndex: 1,
            // 量能柱与 K 线同色（阳红阴绿）：这样「放量下跌」一眼能看出来，
            // 全部涂成中性灰的话量能就只是个装饰（同花顺 / 雪球都是同色）
            data: (trend.value?.ohlc ?? []).map(o => ({
              value: o.volume ?? 0,
              itemStyle: {
                color: o.close >= (o.open ?? o.close) ? rise : fall
              }
            }))
          }
        ]
      : [];
    const maLine = (window: number, token: string, fallback: string) => ({
      name: `MA${window}`,
      type: "line",
      data: movingAverage(candleCloses.value, window),
      symbol: "none",
      smooth: false,
      lineStyle: { width: 1, color: getCssVar(token, fallback) }
    });

    return {
      animation: false,
      tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: [
        { left: 56, right: 16, top: 20, height: 176 },
        { left: 56, right: 16, top: 220, height: hasVolume.value ? 56 : 0 }
      ],
      xAxis: [
        {
          type: "category",
          data: dates,
          boundaryGap: true,
          axisTick: { show: false },
          // 日期轴只画在量能那格，K 线格不重复显示（两格共用同一轴）
          axisLabel: { show: !hasVolume.value, fontSize: 11, hideOverlap: true }
        },
        {
          type: "category",
          gridIndex: 1,
          data: dates,
          boundaryGap: true,
          axisTick: { show: false },
          axisLabel: { fontSize: 11, hideOverlap: true }
        }
      ],
      yAxis: [
        {
          scale: true,
          axisLabel: {
            fontSize: 11,
            formatter: priceAxisLabelFormatter(props.assetType)
          },
          splitLine
        },
        {
          gridIndex: 1,
          splitNumber: 2,
          axisLabel: { show: false },
          splitLine: { show: false }
        }
      ],
      series: [
        {
          name: "K 线",
          type: "candlestick",
          data: candleData.value,
          // 涨红跌绿：color 是阳线、color0 是阴线（与 A 股看盘习惯一致）
          itemStyle: {
            color: rise,
            color0: fall,
            borderColor: rise,
            borderColor0: fall
          }
        },
        maLine(5, CHART_TOKENS.warning, CHART_FALLBACKS.warning),
        maLine(10, CHART_TOKENS.info, CHART_FALLBACKS.info),
        maLine(20, CHART_TOKENS.textTertiary, CHART_FALLBACKS.textTertiary),
        ...volumeSeries
      ]
    };
  }

  // 场外（累计净值，#2171）或没有 OHLCV 的场内：一条线。
  // **不平滑**：平滑会画出实际不存在的峰谷，价格序列上那是失真（#1969）。
  const isReturn = basis.value === "return";
  // 业绩口径画收益率序列（与 values 等长按位对齐），否则画原始净值/收盘价
  const plotValues = isReturn ? returnSeries.value : values;
  const rising =
    plotValues.length >= 2 &&
    plotValues[plotValues.length - 1] >= plotValues[0];
  const lineColor = rising ? rise : fall;
  // 叠加层取色刻意避开 rise（红）/ fall（绿）：买卖点不是涨跌语义，
  // 涂红涂绿会让用户把「我买过」误读成「涨了」。蓝=买入、橙=卖出、
  // 中性灰虚线=成本线——与净值曲线（动态涨跌色）三层不打架（#2171 定稿）。
  const markerBuyColor = getCssVar(CHART_TOKENS.info, CHART_FALLBACKS.info);
  const markerSellColor = getCssVar(
    CHART_TOKENS.warning,
    CHART_FALLBACKS.warning
  );
  const costLineColor = getCssVar(
    CHART_TOKENS.textTertiary,
    CHART_FALLBACKS.textTertiary
  );
  // 清仓竖线用**点线**（成本线是虚线）：它标的是「一轮结束」这个事件，不是价格水平
  const clearingColor = getCssVar(
    CHART_TOKENS.textTertiary,
    CHART_FALLBACKS.textTertiary
  );
  // 业绩口径的 0% 基准线（#2454）：中性灰**实线**——与点线竖线（事件）、
  // 虚线成本线（水平）三层形态分层，不靠颜色区分（色弱用户也读得出）
  const zeroLineColor = getCssVar(
    CHART_TOKENS.textTertiary,
    CHART_FALLBACKS.textTertiary
  );

  /** 轴触发 tooltip：净值行 + 当日成本线 + 当日买卖汇总（#2171）。
      同日多笔在 markerData 已聚合，这里直接显示「N 笔合计」；
      低于当时成本线的点附偏离度（空心编码的文字版，色弱用户也能读到）。

      ⚠️ null 值行必须**整行跳过**（#2454 实测发现的既有缺陷）：成本线在首笔交易前
      为 null（那时还没有持仓成本），ECharts 会把 null 原样放进 params。旧代码
      `Number(p.value)` 把 null 压成 0，tooltip 于是显示一行「成本线：0.0000」——
      把「没有数据」伪装成「成本是 0」，正是设计 §6 禁的造假。业绩口径下同行
      会显示「0.00%」，同样必须跳过。 */
  const tooltipFormatter = (params: Array<Record<string, unknown>>) => {
    if (!params?.length) return "";
    const date = String(params[0].axisValue ?? "");
    const rows: string[] = [`<b>${date}</b>`];
    for (const p of params) {
      const data = (p.data ?? {}) as Record<string, unknown>;
      const seriesName = String(p.seriesName ?? "");
      if (p.seriesType === "scatter") {
        const amount = Number(data.amount ?? 0).toFixed(2);
        const count = Number(data.count ?? 1);
        const merged = count > 1 ? `（${count} 笔合计）` : "";
        const confirm = data.confirm ? `<br/>确认日 ${data.confirm}` : "";
        const closed = data.closed ? " · 当日清仓" : "";
        const deviation = data.deviation as number | null;
        const deviationText =
          deviation === null || deviation === undefined
            ? ""
            : `<br/>${deviation < 0 ? "低于" : "高于"}当时成本 ${Math.abs(deviation).toFixed(2)}%`;
        rows.push(
          `${p.marker ?? ""}${seriesName}${merged}：¥${amount}${closed}${deviationText}${confirm}`
        );
      } else if (isReturn) {
        // 首笔交易前成本线为 null：整行跳过（见 tooltipFormatter 头注释）
        const rawValue = Array.isArray(p.value) ? p.value[1] : p.value;
        if (rawValue === null || rawValue === undefined) continue;
        // 业绩口径（#2454）：主行给收益率，括号附当日净值/收盘价（或成本）——
        // 只看 % 不知道当时多少钱。tooltip 是解释层不是压缩层，两个数都给。
        const idx = Number(p.dataIndex ?? -1);
        const plotted = Number(rawValue);
        const isCost = seriesName === "成本线";
        const orig = isCost ? costSeriesData.value[idx] : values[idx];
        const origLabel = isCost ? "成本" : isCandle.value ? "收盘价" : "净值";
        const origText =
          orig === null || orig === undefined || !Number.isFinite(orig)
            ? ""
            : `（${origLabel} ${formatPrice(orig, props.assetType)}）`;
        rows.push(
          `${p.marker ?? ""}${seriesName}：${formatReturnPercent(plotted)}${origText}`
        );
      } else {
        // 同上：null 行跳过，不把「没有数据」显示成 0
        const rawValue = Array.isArray(p.value) ? p.value[1] : p.value;
        if (rawValue === null || rawValue === undefined) continue;
        const v = Number(rawValue);
        rows.push(
          `${p.marker ?? ""}${seriesName}：${formatPrice(v, props.assetType)}`
        );
      }
    }
    return rows.join("<br/>");
  };

  /**
   * 主系列 markLine 数据（#2171 P2 + #2454）。
   *
   * 清仓轮次竖线与 0% 基准线共用一次 markLine 配置（ECharts 一个系列只能挂一个
   * markLine），但**形态分层**：竖线是点线 + 编号（标事件），基准线是实线 + 无标签
   * （标水平）——不靠颜色区分，色弱用户也读得出。
   */
  const markLineData: Array<Record<string, unknown>> = [];
  if (markersActive.value) {
    for (const m of clearingMarksList.value) {
      markLineData.push({
        xAxis: m.date,
        label: {
          formatter: clearingLabel(m.round, clearingMarksList.value.length),
          position: "insideEndTop"
        }
      });
    }
  }
  if (isReturn) {
    // 0% 基准线：收益率曲线本身从 0 出发，但没有这条线时「高于/低于基准」
    // 要靠眼估刻度——一条实线把上下分区画出来（业绩走势的标准配法）。
    markLineData.push({
      yAxis: 0,
      lineStyle: { color: zeroLineColor, type: "solid", width: 1 },
      label: { show: false }
    });
  }

  return {
    tooltip: { trigger: "axis", formatter: tooltipFormatter },
    grid: { left: 52, right: 16, top: 16, bottom: 28 },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLabel: { fontSize: 11, hideOverlap: true }
    },
    yAxis: {
      type: "value",
      scale: true,
      // 净值 4 位、股价 2 位：不设 formatter 时 echarts 默认只给 1 位，
      // 净值 4.8124 在轴上会显示成 4.8（用户实测反馈）。
      // 业绩口径（#2454）画**带符号百分比**：「+12.3%」比「12.3」多一个「赚了」的确认。
      axisLabel: {
        fontSize: 11,
        formatter: isReturn
          ? (v: number) => formatReturnPercent(v, 1)
          : priceAxisLabelFormatter(props.assetType)
      },
      splitLine
    },
    series: [
      {
        // 场内折线视图画的是**收盘价**（与持仓成本同口径），场外才是净值——
        // 名字不能都叫「净值」，否则场内用户会拿它去对比基金净值（#2171 后续）；
        // 业绩口径（#2454）叫「业绩」：曲线画的是收益率，名字得跟着口径走
        name: isReturn ? "业绩" : isCandle.value ? "收盘价" : "净值",
        type: "line",
        data: plotValues,
        smooth: false,
        symbol: "none",
        lineStyle: { color: lineColor, width: 2 },
        areaStyle: { color: hexToRgba(lineColor, 0.08) },
        // 清仓轮次标记（#2171 P2）：每轮结束画一条点线竖线并编号。
        // `silent: true` —— 它只是刻度，不该抢 tooltip（悬停仍显示当日净值 / 成本 / 买卖）。
        // 业绩口径另含一条 0% 基准线（#2454，见 markLineData 构造处）。
        ...(markLineData.length
          ? {
              markLine: {
                silent: true,
                symbol: ["none", "none"],
                lineStyle: { color: clearingColor, type: "dotted", width: 1 },
                label: { fontSize: 10, color: clearingColor },
                data: markLineData
              }
            }
          : {})
      },
      // 成本线（#2171）：移动加权（含手续费），非交易日前向延续；清仓日断在
      // 最后一笔（costSeriesData 在首笔前为 null，天然不画）。虚线 + 中性灰，
      // 与净值曲线（实线 + 涨跌色）形态分层，不抢主视觉。
      // 业绩口径（#2454）下换算成同基准收益率（costPlotSeries）——y 轴已是 %。
      ...(markersActive.value
        ? [
            {
              name: "成本线",
              type: "line",
              data: costPlotSeries.value,
              symbol: "none",
              smooth: false,
              lineStyle: { color: costLineColor, width: 1, type: "dashed" }
            }
          ]
        : []),
      // 买卖点：三角朝上=买入、朝下=卖出（形状主编码，色弱用户也能分辨）。
      // 低于当时成本线的点改**空心**（填充透明 + 同色描边）：低吸/割肉一眼可辨，
      // 不引入第三种颜色——那会和涨跌语义打架（#2171 P1）。
      ...(markersActive.value
        ? [
            {
              name: "买入",
              type: "scatter",
              // 直径走**每条数据自带**的 symbolSize（#2171 §4.2 弱金额权重）；
              // 系列级那个值退化为兜底——写死它等于把整条点大小规格丢掉（首版就是 9）
              data: sizedMarkers.value.buy.map(m => ({
                ...m,
                itemStyle: m.below
                  ? {
                      color: "transparent",
                      borderColor: markerBuyColor,
                      borderWidth: 1.5
                    }
                  : { color: markerBuyColor }
              })),
              symbol: "triangle",
              symbolSize: UNIFIED_SIZE,
              z: 5
            },
            {
              name: "卖出",
              type: "scatter",
              data: sizedMarkers.value.sell.map(m => ({
                ...m,
                itemStyle: m.below
                  ? {
                      color: "transparent",
                      borderColor: markerSellColor,
                      borderWidth: 1.5
                    }
                  : { color: markerSellColor }
              })),
              symbol: "triangle",
              symbolRotate: 180,
              symbolSize: UNIFIED_SIZE,
              z: 5
            }
          ]
        : [])
    ]
  };
});

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  // 建仓期：显式起始日（首笔买入日）覆盖档位。拿不到起始日（换标的后尚无流水，
  // 或时间线还没回来）时退回 3M——绝不把「建仓」这个前端档位当 range 发给后端。
  const useHolding = range.value === "HOLDING" && firstTradeDate.value !== null;
  try {
    const res = await getProductTrend({
      symbol: props.symbol,
      range: range.value === "HOLDING" ? "3M" : (range.value as TrendRange),
      asset_type: props.assetType,
      ...(useHolding ? { start: firstTradeDate.value as string } : {})
    });
    trend.value = res.data;
  } catch {
    // 拉不到就当无数据：区块降级为空态，不影响详情页其余部分。
    // 与「品类无序列源」（kind 空串，整卡不渲染）是两回事——这里是取数失败，
    // 卡片要留在原处并告知可重试，不能装作「这个品类没有走势」。
    trend.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

// 区块懒加载：走势图数据不阻塞 Hero 渲染（设计 §5 取数编排）
watch(() => props.symbol, load, { immediate: true });
watch(range, load);
// 起始日晚于走势请求回来（时间线是并行拉的）：停在「建仓」档时补一次，
// 避免用上一个标的的起始日画窗口
watch(firstTradeDate, () => {
  if (range.value === "HOLDING") void load();
});
</script>

<template>
  <CardBlock v-if="!noSeries" class="trend-section">
    <SectionHeader title="走势">
      <template #action>
        <!-- ⚠️ 必须自己套一层 flex-wrap 容器（#2039）：SectionHeader 的 action 槽会随窄容器
             收缩，但**只有调用方内层是可折行容器时才会折行**——否则多枚控件直接溢出卡片、
             叠到左侧 ⓘ 上。本区现在是「区间 + 视图 + 3 个复选框」共 5 枚，必须折行。 -->
        <div class="trend-section__actions">
          <SegmentedControl
            v-model="range"
            :options="rangeOptions"
            size="small"
            ariaLabel="切换走势区间"
          />
          <!-- 口径切换（#2454）：净值/价格 vs 业绩（区间累计收益率）。场内外都给——
               「现在多少钱」与「这段时间赚了多少」是两个问题，后者由业绩线答。
               与视图切换**正交**：口径决定 y 轴画什么，视图决定用什么画。 -->
          <SegmentedControl
            v-model="basis"
            :options="basisOptions"
            size="small"
            ariaLabel="切换走势口径"
          />
          <!-- 场内视图切换（#2171 后续）：K 线 / 折线。折线视图让买卖点与成本线能叠上来
               （它们都是「元/股」日序列，只能与折线同轴）；场外只有一条线，不显示该切换器。
               **业绩口径下同样隐藏**（canToggleView 已含 basis 判定）——K 线没有收益率
               画法，留一个点了没反应的选项是假可操作性（#2453 同款纪律）。 -->
          <SegmentedControl
            v-if="canToggleView"
            v-model="candleView"
            :options="TREND_VIEW_OPTIONS"
            size="small"
            ariaLabel="切换走势视图"
          />
          <!-- 买卖点 / 成本线开关（#2171）：有交易点才可开；关掉后只剩曲线。
               默认开——「我买在了哪」是买方核心诉求；信息过载的用户可自行关闭。 -->
          <el-checkbox v-if="hasMarkers" v-model="showMarkers" size="small">
            买卖点
          </el-checkbox>
          <!-- 统一大小（#2171 §4.2）：默认关 = 弱金额权重（看得出大额买入）；
               只想看「我在哪买过」的用户打开它，曲线立刻安静下来。 -->
          <el-checkbox
            v-if="hasMarkers && showMarkers"
            v-model="unifiedSize"
            size="small"
          >
            统一大小
          </el-checkbox>
          <!-- 历轮买卖（#2171 P1）：仅清仓后重建仓的用户可见。关掉只看最近一轮——
               旧轮次的点会让「现在的成本线」难以认读。 -->
          <el-checkbox
            v-if="hasHistoryRounds && showMarkers"
            v-model="showHistoryRounds"
            size="small"
          >
            历轮
          </el-checkbox>
        </div>
      </template>
    </SectionHeader>

    <p v-if="loading" class="trend-section__hint">正在读取走势…</p>

    <p v-else-if="failed" class="trend-section__hint">
      走势读取失败，可稍后重试
    </p>

    <p v-else-if="!hasData" class="trend-section__hint">暂无该区间的历史数据</p>

    <template v-else>
      <v-chart
        :option="chartOption"
        :autoresize="true"
        class="trend-section__chart"
      />
      <p v-if="spanNotice" class="trend-section__hint">{{ spanNotice }}</p>
      <!-- 买卖点开关被视图挡住时给一句明话（#2453）：开关不渲染 + 一句话解释，
           比留一个点了没反应的勾选框诚实，也让「折线视图为什么存在」有答案。 -->
      <p v-if="tradesHiddenByView" class="trend-section__hint">
        买卖点与成本线在「折线」视图中叠加显示
      </p>
      <!-- 来源说「哪个网站」，口径说「怎么算的」——后端分开给，前端只排版，
           不在这里推断「close 就等于前复权」（#1969）。
           空心买卖点（#2171 P1）：成交价低于当时持仓成本——低吸 / 割肉。 -->
      <p class="trend-section__footnote">
        数据日期：{{ trend?.dates?.[0] }} 至
        {{ trend?.dates?.[trend.dates.length - 1] }}
        <template v-if="trend?.source">
          · 数据来源：{{ trend.source }}（{{ trend.basis }}）
        </template>
        <!-- 业绩口径（#2454）：口径说明——基准是区间首日（不是成立以来），
             与「这段时间赚了多少」这个问题对齐；成立以来收益归业绩卡，不重复造。 -->
        <template v-if="basis === 'return'">
          · 业绩以区间首日{{ isCandle ? "收盘价" : "净值" }}为基准
        </template>
        <template v-if="hasMarkers"> · 空心△ = 低于当时成本</template>
      </p>
    </template>

    <!-- 累计收益面板（#2171 P1）：全程累计已实现 + 紧凑统计条。
         有流水才渲染；数据来自与叠加层同一次时间线请求，不重复取数。 -->
    <ProductProfitPanel v-if="hasTrades" :timeline="timeline" />
  </CardBlock>
</template>

<style scoped>
.trend-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.trend-section__chart {
  width: 100%;

  /* K 线格 + 量能格叠放（见 chartOption 的 grid 高度），故比单线图高一截 */
  height: 300px;
}

.trend-section__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.trend-section__footnote {
  margin: 0;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* action 槽的内层容器：**必须可折行**（#2039）。SectionHeader 的槽会收缩，但只有在
   调用方内层 `flex-wrap: wrap` 时才折行——否则区间/视图/复选框一排直接溢出卡片。
   `justify-content: flex-end` 让折行后仍贴右对齐，宽屏下与折行前逐像素一致。 */
.trend-section__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2, 8px);
  align-items: center;
  justify-content: flex-end;
}
</style>
