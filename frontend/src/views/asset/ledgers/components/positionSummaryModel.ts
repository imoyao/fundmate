/**
 * 持仓抽屉的数值口径（#980 拆分自 `PositionTransactionsDrawer.vue`）。
 *
 * 原来 8 张描边卡片逐个手写在模板里，差异只有「标签 / 单位 / 是否加载中」。
 * 按设计 `docs/design/product-detail-drawer.md` §4 / §6.2 收敛为：
 * 一个锚点（持仓市值 + 盈亏副行）+ 5 项键值网格（无边框无底色）。
 * 数字只有三档：24（锚点）/ 14（键值）/ 13（标签），本模型只产出「值与单位」，
 * 字号由渲染层决定。
 */
import { pricePrecision } from "@/utils/pricePrecision";

/** 持仓抽屉需要的字段子集（后端 /api/positions 行） */
export interface PositionLike {
  id?: number | string;
  name?: string | null;
  symbol?: string | null;
  type_label?: string | null;
  asset_type?: string | null;
  /** 市场（部分品类有；持仓表不存 venue，故只带 market 去问后端） */
  market?: string | null;
  quantity?: number | null;
  avg_price?: number | null;
  current_price?: number | null;
  market_value?: number | null;
  pnl?: number | null;
  pnl_rate?: number | null;
  /** 本轮持有时长（天），后端按 confirm_date 计算（#862） */
  holding_days?: number | null;
}

/** 一项键值（渲染成 `.pd-fact`，无边框无底色） */
export interface PositionFact {
  key: string;
  /** 标签（注解就近放在标签里，如「持有时长(本轮)」） */
  label: string;
  /** 纯文本值（与 money 二选一） */
  text?: string;
  /** 金额值（走 MoneyDisplay） */
  money?: number;
  /** MoneyDisplay 精度（不传用组件默认） */
  precision?: number;
  /** MoneyDisplay 是否带正负号 */
  showSign?: boolean;
  /** MoneyDisplay 是否按正负自动着色 */
  autoColor?: boolean;
  /** 值后缀小字（份 / 元/份 / 股/张） */
  unit?: string;
  /** 值颜色（不传走 --text-primary） */
  color?: string;
  /** 非空时替代数值显示的占位文案（如「计算中…」） */
  pending?: string;
}

/** 锚点：主数值（持仓市值）+ 副行（盈亏额 / 盈亏率 / 年化） */
export interface PositionAnchor {
  /** 持仓市值（元）；无数据为 null（MoneyDisplay 渲染占位） */
  value: number | null;
  /** 副行是否有内容——没有就整段不渲染 */
  hasSub: boolean;
  /** 持仓盈亏（元） */
  pnl: number | null;
  /** 盈亏率（%） */
  pnlRate: number | null;
  /** 盈亏不可得时退而展示年化（有值才用） */
  xirr: number | null;
  /** 年化是否计算中 */
  xirrLoading: boolean;
}

/** 基金 / 货币基金：份额单位用「份」、价格单位用「元/份」 */
export function isFundPosition(assetType?: string | null): boolean {
  return ["fund", "money_fund"].includes(assetType ?? "");
}

/** 年化收益率（XIRR）文本：带符号、两位小数；无数据为 -- */
export function formatXirr(xirr: number | null | undefined): string {
  if (xirr == null) return "--";
  return `${xirr >= 0 ? "+" : ""}${(xirr * 100).toFixed(2)}%`;
}

/** 年化收益率颜色：无数据用主文字色，其余按涨跌 */
export function xirrColor(xirr: number | null | undefined): string {
  if (xirr == null) return "var(--text-primary)";
  return xirr >= 0 ? "var(--color-rise)" : "var(--color-success)";
}

/**
 * 锚点模型（§6.2：「持仓盈亏 + 盈亏率两张卡」并成一条副行）。
 *
 * 副行的存在条件：盈亏额或盈亏率任一可得。两者都缺时，如果年化有值就用年化顶上
 * （否则副行整段不渲染，读者分不清「没数据」还是「没算完」）；年化仍在计算中则显式
 * 写「计算中…」——这是设计 §6.3 明确要求保留的一处文案。
 */
export function buildAnchor(
  position: PositionLike | null | undefined,
  xirr: number | null,
  xirrLoading: boolean
): PositionAnchor {
  const p = position ?? {};
  const pnl = p.pnl ?? null;
  const pnlRate = p.pnl_rate ?? null;
  const hasPnl = pnl != null || pnlRate != null;
  return {
    value: p.market_value ?? null,
    hasSub: hasPnl || xirr != null || xirrLoading,
    pnl,
    pnlRate,
    xirr,
    xirrLoading
  };
}

/**
 * 5 项键值网格：持有份额/数量 · 持仓成本 · 最新净值/现价 · 持有时长(本轮) · 年化收益率。
 *
 * 「市值 / 盈亏 / 盈亏率」已升到锚点，不在这里重复（§6.2：同一个问题不答两遍）。
 * `xirrLoading` 为 true 时最后一项显示「计算中…」而不是 `--`，否则用户会把
 * 「还没算完」误读成「算不出来」。
 */
export function buildFacts(
  position: PositionLike | null | undefined,
  xirr: number | null,
  xirrLoading: boolean
): PositionFact[] {
  const p = position ?? {};
  const fund = isFundPosition(p.asset_type);
  /** 成本 / 净值按品类精度显示（基金 4 位、股票 2 位，见 pricePrecision） */
  const precision = pricePrecision(p.asset_type);

  return [
    {
      key: "quantity",
      label: fund ? "持有份额" : "持有数量",
      text: Number(p.quantity ?? 0).toLocaleString(),
      unit: fund ? "份" : "股/张"
    },
    {
      key: "cost",
      label: "持仓成本",
      money: p.avg_price || 0,
      precision,
      showSign: false,
      autoColor: false,
      unit: fund ? "元/份" : "元"
    },
    {
      key: "price",
      label: fund ? "最新净值" : "现价",
      money: p.current_price || 0,
      precision,
      showSign: false,
      autoColor: false,
      unit: fund ? "元/份" : "元"
    },
    {
      // 「(本轮)」进标签：它是口径说明，不是独立指标
      key: "holding_days",
      label: "持有时长(本轮)",
      text: p.holding_days != null ? `${p.holding_days} 天` : "--"
    },
    {
      key: "xirr",
      label: "年化收益率",
      text: formatXirr(xirr),
      color: xirrColor(xirr),
      pending: xirrLoading ? "计算中…" : undefined
    }
  ];
}
