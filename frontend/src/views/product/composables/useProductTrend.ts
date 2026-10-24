// 产品详情页「走势」区块的状态与派生（#980 拆分，源自 ProductTrendSection.vue）。
//
// 只做状态与派生，不碰 DOM / ECharts 配置：
// - 区间与口径（净值 vs 区间累计收益率）→ `trendBasisMetrics`
// - 视图三判定（切换器是否可见 / 量能副图 / 叠加层是否可用）→ `trendViewMetrics`
// - 买卖点直径公式 → `trendMarkerMetrics`
// 图表配置在 `../components/trendChartOption.ts`，模板在 `ProductTrendSection.vue`。
import { computed, ref, watch, type Ref } from "vue";
import {
  getProductTrend,
  getTradeTimeline,
  type ProductTrendResult,
  type TradeTimelineResult,
  type TrendRange
} from "@/api/products";
import {
  effectiveUseCandle,
  overlayAvailable,
  showViewToggle,
  showVolumeSeries,
  type TrendView
} from "../components/trendViewMetrics";
import {
  toCumulativeReturn,
  toReturnPct,
  trendBasisOptions,
  type TrendBasis
} from "../components/trendBasisMetrics";
import {
  SELL_SIZE_RATIO,
  UNIFIED_SIZE,
  clearingMarks,
  markerMaxSize,
  markerSize,
  maxAmountOf
} from "../components/trendMarkerMetrics";
import { useThemeTick } from "@/composables/echarts/theme";

export interface UseProductTrendOptions {
  symbol: Ref<string>;
  /** 仅持有时拉交易时间线（流水是私有数据） */
  hasPosition: Ref<boolean | undefined>;
  /** 品类：决定收盘价 / 净值口径 */
  assetType: Ref<string | undefined>;
}

export function useProductTrend(options: UseProductTrendOptions) {
  const { symbol, hasPosition, assetType } = options;

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
    () =>
      showViewToggle(trend.value?.ohlc?.length ?? 0) && basis.value === "nav"
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
    if (!symbol.value || hasPosition.value !== true) {
      timeline.value = null;
      return;
    }
    try {
      const res = await getTradeTimeline({ symbol: symbol.value });
      timeline.value = res.data;
    } catch {
      timeline.value = null;
    }
  }

  // 时间线不分区间（全量重放），symbol / 持有状态变化才重拉
  watch(() => [symbol.value, hasPosition.value], loadTimeline, {
    immediate: true
  });

  /** 首笔交易日（建仓期区间的起点；无流水为 null） */
  const firstTradeDate = computed(
    () => timeline.value?.summary.first_trade_date ?? null
  );

  /** 区间选项：有流水才追加「建仓」（没买过就没有建仓期可言） */
  const rangeOptions = computed(() =>
    firstTradeDate.value
      ? [
          ...RANGE_BASE_OPTIONS,
          { label: "建仓", value: "HOLDING" as RangeValue }
        ]
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
      basis.value === "return"
        ? returnSeries.value
        : (trend.value?.values ?? []);
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
    const m = new Map(
      visibleCostLine.value.map(c => [c.date, c.avg_cost_yuan])
    );
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
  async function load() {
    if (!symbol.value) return;
    loading.value = true;
    failed.value = false;
    // 建仓期：显式起始日（首笔买入日）覆盖档位。拿不到起始日（换标的后尚无流水，
    // 或时间线还没回来）时退回 3M——绝不把「建仓」这个前端档位当 range 发给后端。
    const useHolding =
      range.value === "HOLDING" && firstTradeDate.value !== null;
    try {
      const res = await getProductTrend({
        symbol: symbol.value,
        range: range.value === "HOLDING" ? "3M" : (range.value as TrendRange),
        asset_type: assetType.value,
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
  watch(symbol, load, { immediate: true });
  watch(range, load);
  // 起始日晚于走势请求回来（时间线是并行拉的）：停在「建仓」档时补一次，
  // 避免用上一个标的的起始日画窗口
  watch(firstTradeDate, () => {
    if (range.value === "HOLDING") void load();
  });

  return {
    // 模板直接用
    range,
    rangeOptions,
    loading,
    failed,
    trend,
    noSeries,
    hasData,
    isCandle,
    candleView,
    basis,
    basisOptions,
    canToggleView,
    showMarkers,
    unifiedSize,
    showHistoryRounds,
    hasHistoryRounds,
    hasMarkers,
    markersActive,
    tradesHiddenByView,
    hasTrades,
    spanNotice,
    timeline,
    // 图表配置用（trendChartOption 的入参）
    themeTick,
    hasVolume,
    candleCloses,
    candleData,
    returnSeries,
    useCandle,
    clearingMarksList,
    costPlotSeries,
    costSeriesData,
    sizedMarkers
  };
}
