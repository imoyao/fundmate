// src/views/welcome/composables/todayPnlOverlay.ts
/**
 * 盘中「价格替换」：把实时行情对当日盈亏的影响叠到后端结果上（纯函数）。
 *
 * ## 为什么是「换价」而不是「重算」
 *
 * 当日盈亏口径只有后端一条（`services/pnl_calendar` 的 `total_pnl` 日差分，
 * 含 as-of 份额、建仓日剔除、估值定格回退）。前端若拿持仓 × (现价 − 昨收) 自己算，
 * 就会得到第二套数字：卖出过的、当日建仓的、外币的都会分叉，收盘那一刻还会
 * 「跳」一下才对上。
 *
 * 这里只做一件事：后端已经给了每笔持仓的**当日取价** `holding.price`，
 * 实时行情只是把那个价换掉——增量 = `(实时价 − 当日价) × 份额`。
 * 于是：
 *   · 实时价 === 当日价时，增量恒 0（不会凭空多出几块钱）；
 *   · 收盘停跳后回到后端值，天然收敛，不需要「对齐」；
 *   · 分项与合计同步加同一个增量，`Σ 分项 ≡ 合计` 继续成立。
 *
 * 状态一律转 `estimated`：盘中/收盘估值的数都还不是官方值，卡面要挂「估」。
 */

import type {
  TodayPnlClass,
  TodayPnlData,
  TodayPnlHolding
} from "@/api/summary";

const round2 = (n: number): number => Math.round(n * 100) / 100;

export interface OverlayResult {
  data: TodayPnlData;
  /** 是否真的替换了至少一笔价格（false ⇒ 调用方沿用后端原值，不做任何展示差异） */
  applied: boolean;
}

export interface OverlayOptions {
  /**
   * 后端给的是「最近交易日」（`is_today=false`，盘中 / 净值未出）时必须为 true。
   *
   * 此时后端那笔盈亏是**昨天**的，而实时增量是「现价 − 昨日收盘」＝**今天**的收益。
   * 两者相加等于「昨天的收益 + 今天的浮盈」，是两天的数被叠成一天；
   * 正确形态是把增量当作今天的全量收益（base 取 0）。
   */
  replaceBase?: boolean;
  /** 今日 ISO 日期（上海时区）：替换模式下把 `date` / `is_today` 改写为今天 */
  todayIso?: string;
}

/** 大类分项在替换后的派生字段（盈亏 / 收益率 / 市值） */
function applyClassDelta(
  item: TodayPnlClass,
  delta: number,
  replaceBase: boolean,
  hasQuote: boolean
): TodayPnlClass {
  // 替换模式 + 该大类今天一笔行情都没拿到 ⇒ 今天是「没有数」，不是「0.00」。
  // （非替换模式不动：后端那笔数本身是当天的，缺价的部分早已在 `pnl` 里处理）
  if (replaceBase && !hasQuote) {
    return { ...item, pnl: null, rate: null, status: "partial" };
  }
  const basePnl = replaceBase ? 0 : (item.pnl ?? 0);
  const baseValue = item.market_value ?? 0;
  // 前一基准日市值 = 当日市值 − 当日盈亏（份额不变时恒等；当日有买卖时是近似，
  // 且只影响盘中展示的百分比，收盘即回后端口径）
  const prevValue = baseValue - basePnl;
  const pnl = round2(basePnl + delta);
  return {
    ...item,
    pnl,
    rate: prevValue > 0 ? round2((pnl / prevValue) * 100) : item.rate,
    market_value: round2(baseValue + delta),
    status: "estimated"
  };
}

/** 上海时区的今日 ISO 日期（`en-CA` 恰好输出 YYYY-MM-DD，不依赖本地时区） */
export function shanghaiTodayIso(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(
    now
  );
}

/**
 * @param prices 实时行情（symbol → 元）；缺失 / 非法价的标的不参与替换
 * @param options `replaceBase` 见 {@link OverlayOptions}（后端日期不是今天时必须开）
 */
export function applyPriceOverlay(
  data: TodayPnlData,
  prices: Map<string, number>,
  options: OverlayOptions = {}
): OverlayResult {
  const holdings: TodayPnlHolding[] = data.holdings ?? [];
  if (holdings.length === 0 || prices.size === 0) {
    return { data, applied: false };
  }

  const deltaByClass: Record<string, number> = {};
  // 有大类拿到了有效实时价（哪怕价格没动）——用于区分「今天没动」与「今天没数」
  const quoted = new Set<string>();
  let applied = false;
  for (const holding of holdings) {
    const price = prices.get(holding.symbol);
    if (!Number.isFinite(price) || (price as number) <= 0) continue;
    if (!Number.isFinite(holding.price) || holding.price <= 0) continue;
    if (!Number.isFinite(holding.quantity) || holding.quantity <= 0) continue;
    quoted.add(holding.class);
    const delta = ((price as number) - holding.price) * holding.quantity;
    if (delta === 0) continue;
    deltaByClass[holding.class] = (deltaByClass[holding.class] ?? 0) + delta;
    applied = true;
  }

  const replaceBase = options.replaceBase === true;
  // 替换模式下即使增量全为 0 也要改写（今天的 0 与昨天的收益是两件事）
  if (!applied && !(replaceBase && quoted.size > 0)) {
    return { data, applied: false };
  }

  const classes = data.classes.map(item =>
    applyClassDelta(
      item,
      deltaByClass[item.key] ?? 0,
      replaceBase,
      quoted.has(item.key)
    )
  );
  const totalPnl = round2(
    classes.reduce((sum, item) => sum + (item.pnl ?? 0), 0)
  );
  const invested = round2(
    classes.reduce((sum, item) => sum + (item.market_value ?? 0), 0)
  );
  const baseInvested = data.invested_value ?? invested;
  // 替换模式下分母是「上一收盘市值」（= 当日市值），不是「昨日市值 − 昨日收益」
  const basePnl = replaceBase ? 0 : (data.total_pnl ?? 0);
  const prevTotal = baseInvested - basePnl;

  return {
    applied: true,
    data: {
      ...data,
      // 替换模式下这批数属于**今天**，日期标签必须跟着改，否则卡面会写
      // 「最近交易日 11月2日」却显示今天的浮盈（标签与数字互相矛盾）
      date: replaceBase && options.todayIso ? options.todayIso : data.date,
      is_today: replaceBase ? true : data.is_today,
      classes,
      total_pnl: totalPnl,
      total_rate:
        prevTotal > 0 ? round2((totalPnl / prevTotal) * 100) : data.total_rate,
      invested_value: invested,
      status: "estimated"
    }
  };
}

/**
 * 副标题（口径 + 时间）：一件事一句话，不堆术语。
 *
 * - 盘中替换过 ⇒ 「盘中估值 · 更新于 HH:mm」
 * - 收盘估值待确认 ⇒ 「收盘估值 · 官方净值公布后自动确认」
 * - 已确认 ⇒ 「官方净值已确认」
 * - 部分标的没出价 ⇒ 「部分标的本日尚无报价」
 * - 今天还没有任何当日价 ⇒ 「最近交易日 M月D日」（不许拿昨天的数当今天）
 */
export function todayPnlSubtitle(input: {
  status: TodayPnlData["status"];
  isToday: boolean;
  date: string;
  updateTime?: string;
}): string {
  if (input.status === "estimated") {
    return input.updateTime
      ? `盘中估值 · 更新于 ${input.updateTime}`
      : "收盘估值 · 官方净值公布后自动确认";
  }
  if (!input.isToday) {
    return `最近交易日 ${formatMonthDay(input.date)}`;
  }
  if (input.status === "confirmed") return "官方净值已确认";
  if (input.status === "partial") return "部分标的本日尚无报价";
  return "";
}

/** ISO 日期 → 「M月D日」（不引入时区换算：日期本身就是上海时区的交易日标签） */
export function formatMonthDay(iso: string): string {
  const m = iso?.match(/^\d{4}-(\d{2})-(\d{2})$/);
  if (!m) return iso ?? "";
  return `${Number(m[1])}月${Number(m[2])}日`;
}
