import { computed, watch, type Ref } from "vue";
import { useRealtimeQuotes } from "@/composables/useRealtimeQuotes";
import { VENUE_OTC, venueOfAssetType } from "@/constants/market";
import type { Holding, ValuationItem } from "@/utils/valuationEngine";

/**
 * 持仓「盈亏双线」的估值接线（#1104）。
 *
 * ## 两条口径从哪来
 *
 * - **已确认盈亏**（主）：后端 `positions.current_price` —— 场外是已公布确认净值、
 *   场内是最近交易日收盘价，由同步任务 `position_price` 回写（PR #1595 / #1654，
 *   决策见 `docs/spec/decisions.md` 2026-09-18）。本文件只做 `(现价 − 成本) × 份额`
 *   的展示层运算，不改后端数据。
 * - **当日预估盈亏**（辅）：前端实时链路（`useRealtimeQuotes` → 天天基金估值 / 腾讯行情）。
 *   后端**不落库、不维护**预估口径 —— 两种口径混写会让「确认价 / 估值价」不可区分。
 *
 * ## 为什么两条线必须同时可辨
 *
 * 用户对不上账时，第一个怀疑的是整个账本。因此：预估永远带「估」标记（文案见
 * `ESTIMATE_DISCLAIMER`），且**在拿不到真实行情时不显示数字**（见 `estimatedPnl`）。
 */

/** 参与估值所需的持仓最小字段集（`Position` 与自选行都可满足） */
export interface ValuatedPosition {
  symbol?: string | null;
  /** 资产类型（后端 asset_type：stock / etf / bond / fund / money_fund …） */
  type?: string | null;
  quantity?: number | null;
  avg_price?: number | null;
  current_price?: number | null;
}

/**
 * 可实时估值的资产类型白名单。
 *
 * 用白名单而非黑名单：`positions` 里还有虚拟币 / 指数 / 投顾组合 / 经理 / 现金等
 * **没有可交易现价**的类型，黑名单会随枚举扩张而漏（#1171 枚举漂移）。宁可不显示，
 * 也不要拿一个不相干的代码去行情源换回一个看起来像价格的数字。
 *
 * 货基（`money_fund`）不在表内：它每份恒 1 元、收益走万份收益，行情源给的是
 * 场外净值，拿来算盈亏是错值（同 `position_price` job 的处理口径）。
 */
const ESTIMATABLE_TYPES = new Set(["stock", "etf", "bond", "fund"]);

/**
 * `(现价 − 成本) × 份额` 这个盈亏口径**不成立**的类型。
 *
 * - 货基：每份净值恒 1 元，收益体现在万份收益；用净值差算恒等于 0，
 *   在表格里就是「市值 5 万、盈亏 ¥0.00」这种看着像坏了的行；
 * - 逆回购：现金等价物，按实际占款天数计息，市价恒为面值。
 *
 * 两者都返回 `null`（展示 `--`）而不是 0 —— 「没这个口径」和「这个口径算出来是 0」
 * 是两件事，混在一起会让人以为账是对的（#1104 的原始症状正是「盈亏恒为 0」）。
 */
const NON_PNL_TYPES = new Set(["money_fund", "reverse_repo"]);

/** 预估口径的免责文案。放在数字旁（「估」标记的 tooltip）与区块说明共用同一份。 */
export const ESTIMATE_DISCLAIMER =
  "预估：按最新披露持仓与实时行情估算，最终以基金公司公布净值为准";

/** 区块标题的信息图标文案：一次说清两条线各自是什么。 */
export const PNL_DUAL_SCOPE_TIP =
  "已确认＝最近一次公布的确认净值 / 收盘价（权威、可复算）；" +
  "预估＝盘中按实时行情估算，仅作参考，会随行情跳动。";

/** 资产类型 → 行情源所需的 stock / fund 二分（与自选页 `getHoldings` 同口径） */
export function realtimeQuoteType(p: ValuatedPosition): "stock" | "fund" {
  const type = (p.type || "").trim().toLowerCase();
  if (type === "fund") return "fund";
  return venueOfAssetType(type) === VENUE_OTC ? "fund" : "stock";
}

/** 该持仓能否产出「当日预估」：类型可估值 + 有代码 + 有数量 */
export function isEstimatable(p: ValuatedPosition): boolean {
  const type = (p.type || "").trim().toLowerCase();
  if (!ESTIMATABLE_TYPES.has(type)) return false;
  if (!p.symbol) return false;
  return Number(p.quantity ?? 0) > 0;
}

/**
 * 已确认盈亏（T-1 口径）＝（`current_price` − `avg_price`）× 数量。
 *
 * 现价或成本缺失 / 为 0 时返回 `null`（展示为 `--`）而不是当作 0 参与运算：
 * `current_price === 0` 表示后端还没刷到价，按 0 算会把「无数据」显示成「亏光本金」。
 * 货基 / 逆回购同样返回 `null`（见 `NON_PNL_TYPES`）。
 */
export function confirmedPnl(p: ValuatedPosition): number | null {
  const type = (p.type || "").trim().toLowerCase();
  if (NON_PNL_TYPES.has(type)) return null;
  const quantity = Number(p.quantity ?? 0);
  const current = Number(p.current_price ?? 0);
  const avg = Number(p.avg_price ?? 0);
  if (!(quantity > 0) || !(current > 0) || !(avg > 0)) return null;
  return (current - avg) * quantity;
}

export function usePositionValuation(positions: Ref<ValuatedPosition[]>) {
  const getHoldings = (): Holding[] =>
    positions.value.filter(isEstimatable).map(p => ({
      symbol: p.symbol as string,
      type: realtimeQuoteType(p),
      quantity: Number(p.quantity ?? 0),
      costPrice: Number(p.avg_price ?? 0)
    }));

  const getStaticPrice = (symbol: string) => {
    const hit = positions.value.find(p => p.symbol === symbol);
    return hit ? { currentPrice: Number(hit.current_price ?? 0) } : undefined;
  };

  const realtime = useRealtimeQuotes(getHoldings, getStaticPrice);

  const estimateBySymbol = computed(() => {
    const map = new Map<string, ValuationItem>();
    for (const item of realtime.items.value) map.set(item.symbol, item);
    return map;
  });

  /**
   * 当日预估盈亏。**只有真正拿到实时 / 估值行情时才返回数值**。
   *
   * `source === "static"` 是引擎在行情不可达时回退到后端 `current_price` 的降级路径——
   * 那个值就是「已确认」口径本身。若照原样显示在副行，用户会看到两行一模一样的数字，
   * 却以为是两个独立结论；这比不显示更糟（`valuationEngine` 的 `source` 字段正是为此存在）。
   */
  function estimatedPnl(p: ValuatedPosition): number | null {
    if (!isEstimatable(p)) return null;
    const item = estimateBySymbol.value.get(p.symbol as string);
    if (!item || item.source !== "realtime" || !(item.currentPrice > 0)) {
      return null;
    }
    return (
      (item.currentPrice - Number(p.avg_price ?? 0)) * Number(p.quantity ?? 0)
    );
  }

  /**
   * 预估拿不到时的副行提示，区分三种原因。
   *
   * 「品种不参与」优先于「没开开关」：货基 / 逆回购即使开了实时也永远没有预估，
   * 若先说「未开启实时估值」，用户去开了开关还是看不到数，等于把人引到死胡同。
   *
   * 文案取短句（不带操作指引）：开关就在同区块标题行上，逐行复述「开启实时估值
   * 可看当日预估」会让整列变成复读机。
   */
  function estimateHint(p: ValuatedPosition): string {
    if (!isEstimatable(p)) return "该品种不参与实时估值";
    if (!realtime.enabled.value) return "未开启实时估值";
    return "实时行情暂不可用";
  }

  const toggleText = computed(() =>
    realtime.enabled.value ? "关闭实时估值" : "开启实时估值"
  );

  /**
   * 持仓集合变化（翻页 / 增删 / 全局刷新）时重取估值。
   *
   * `useRealtimeQuotes` 只在启动与轮询 tick 时调 `getHoldings`，不监听入参变化；
   * 不补这一条，翻页后副行仍是上一页的行情 —— 每个代码都还是合法价格，静默错值。
   */
  watch(positions, () => {
    if (realtime.enabled.value) void realtime.manualRefresh();
  });

  return {
    realtime,
    toggleText,
    estimatedPnl,
    estimateHint
  };
}

export type PositionValuation = ReturnType<typeof usePositionValuation>;
