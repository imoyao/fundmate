/**
 * 家庭级基金风格分布的展示口径（#2628）。
 *
 * 后端 `services/fund_style_service.portfolio_style_exposure` 已经把三件事定死：
 * 按持仓市值加权、无风格箱的基金**不计入加权但计入分母**、覆盖率单独给。
 * 前端**不二次推导**，本文件只做展示层的三件事：
 *
 * 1. 把 8 个风格排成条形——各风格合计 100，故暴露值可直接当条形宽度百分比；
 * 2. 标出唯一的「领先风格」（只给这一个上强调色，其余中性，避免整屏都在喊）；
 * 3. 未覆盖清单的折叠摘要——不补 0、不藏起来（#2617 的纪律）。
 */
import type { FundStyleItem, PortfolioStyleExposure } from "@/api/funds";

export interface StyleBar {
  name: string;
  /** 暴露值 0-100；null 归一为 0（后端 null = 该时点该风格缺失） */
  value: number;
  /** 条形宽度百分比（= 暴露值，因为 8 个风格合计 100） */
  widthPct: number;
  /** 是否为领先风格（页面里唯一用强调色的那一条） */
  isLead: boolean;
}

/**
 * 构造条形数据。
 *
 * 全 0 时**不**把第一条标成领先：那会凭空造出一个「主导风格」，
 * 与后端「无源即不派生」的取舍冲突。
 */
export function buildStyleBars(
  styles: FundStyleItem[] | null | undefined
): StyleBar[] {
  const items = (styles ?? []).map(item => ({
    name: item.style_name,
    value: Number(item.value ?? 0)
  }));
  const max = items.reduce((acc, item) => Math.max(acc, item.value), 0);
  return items.map(item => ({
    name: item.name,
    value: item.value,
    widthPct: Math.max(0, Math.min(100, item.value)),
    isLead: max > 0 && item.value === max
  }));
}

/** 领先风格名；全 0 或无数据返回 null */
export function leadStyleLabel(bars: StyleBar[]): string | null {
  return bars.find(bar => bar.isLead)?.name ?? null;
}

/**
 * 覆盖率文案。
 *
 * 覆盖率可能很小（首批只有几只基金有箱体，实测 8.35%），两位小数比取整更有信息量；
 * 但到两位数百分比后小数位就不再重要，取整避免「41.84%」这类假精度。
 */
export function formatCoverage(pct: number): string {
  if (!Number.isFinite(pct) || pct <= 0) return "0%";
  // 只去**小数**尾零。直接对 "100" 跑 /0+$/ 会把它削成 "1"（实测踩过），
  // 所以整数分支原样返回，小数分支才裁剪。
  const text =
    pct >= 10
      ? pct.toFixed(0)
      : pct.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  return `${text}%`;
}

/** 未覆盖清单的折叠摘要：前 N 只 + 剩余只数 */
export function uncoveredSummary(
  items: PortfolioStyleExposure["uncovered"] | null | undefined,
  limit = 5
): { shown: PortfolioStyleExposure["uncovered"]; restCount: number } {
  const list = items ?? [];
  return {
    shown: list.slice(0, limit),
    restCount: Math.max(0, list.length - limit)
  };
}

/** 「算不出来」的判据：styles 为空数组（后端明示 ≠ 全部为 0） */
export function isStyleEmpty(
  data: PortfolioStyleExposure | null | undefined
): boolean {
  return !data || !Array.isArray(data.styles) || data.styles.length === 0;
}

/** 箱体时点区间文案：各基金取各自最新时点，可能跨月 */
export function periodLabel(
  data: PortfolioStyleExposure | null | undefined
): string | null {
  if (!data?.period_to) return null;
  if (!data.period_from || data.period_from === data.period_to) {
    return data.period_to;
  }
  return `${data.period_from} ~ ${data.period_to}`;
}
