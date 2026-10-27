/**
 * 持仓抽屉的摘要卡片口径（#980 拆分自 `PositionTransactionsDrawer.vue`）。
 *
 * 8 张卡片原先逐个手写在模板里（约 190 行），差异只有「标签 / 单位 / 是否加载中」。
 * 这里统一成数据，模板只负责渲染——文案、单位与颜色规则原样保留，便于单测断言。
 */
import { pricePrecision } from "@/utils/pricePrecision";

/** 持仓抽屉需要的字段子集（后端 /api/positions 行） */
export interface PositionLike {
  id?: number | string;
  name?: string | null;
  symbol?: string | null;
  type_label?: string | null;
  asset_type?: string | null;
  quantity?: number | null;
  avg_price?: number | null;
  current_price?: number | null;
  market_value?: number | null;
  pnl?: number | null;
  pnl_rate?: number | null;
  /** 本轮持有时长（天），后端按 confirm_date 计算（#862） */
  holding_days?: number | null;
}

/** 一张摘要卡片的渲染数据 */
export interface SummaryCell {
  key: string;
  label: string;
  /** 标签后缀小字（如「(本轮)」） */
  labelHint?: string;
  /** 纯文本值（与 money 二选一） */
  text?: string;
  /** 金额值（走 MoneyDisplay） */
  money?: number;
  /** MoneyDisplay 精度（不传用组件默认） */
  precision?: number;
  /** MoneyDisplay 是否带正负号 */
  showSign?: boolean;
  /** MoneyDisplay 是否按正负自动着色（不传用组件默认：会着色） */
  autoColor?: boolean;
  /** 值后缀小字（份 / 元 / 股/张） */
  unit?: string;
  /** 值颜色（不传走 --text-primary） */
  color?: string;
  /** 卡片底部提示 */
  hint?: string;
  /** 非空时替代数值显示的占位文案（如「计算中…」） */
  pending?: string;
}

/** 基金 / 货币基金：份额单位用「份」、价格单位用「元/份」 */
export function isFundPosition(assetType?: string | null): boolean {
  return ["fund", "money_fund"].includes(assetType ?? "");
}

/** 盈亏率文本：带符号、两位小数；无数据为 -- */
export function formatPnlRate(rate: number | null | undefined): string {
  if (rate == null) return "--";
  return `${rate >= 0 ? "+" : ""}${rate.toFixed(2)}%`;
}

/** 盈亏率颜色：非负数用涨色（null 也算涨色，与拆分前一致） */
export function pnlRateColor(rate: number | null | undefined): string {
  return (rate ?? 0) >= 0 ? "var(--color-rise)" : "var(--color-success)";
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
 * 组装 8 张摘要卡。
 *
 * `xirrLoading` 为 true 时最后一张显示「计算中…」而不是 `--`——
 * 否则用户会把「还没算完」误读成「算不出来」。
 */
export function buildSummaryCells(
  position: PositionLike | null | undefined,
  xirr: number | null,
  xirrLoading: boolean
): SummaryCell[] {
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
      key: "market_value",
      label: "市值",
      money: p.market_value || 0,
      showSign: false,
      autoColor: false
    },
    {
      // 盈亏金额按正负自动着色（不传 autoColor，沿用 MoneyDisplay 默认）
      key: "pnl",
      label: "持仓盈亏",
      money: p.pnl || 0
    },
    {
      key: "pnl_rate",
      label: "盈亏率",
      text: formatPnlRate(p.pnl_rate),
      color: pnlRateColor(p.pnl_rate)
    },
    {
      key: "holding_days",
      label: "持有时长",
      labelHint: "(本轮)",
      text: p.holding_days != null ? `${p.holding_days} 天` : "--",
      hint: "清仓后重新计起，不累计历史"
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
