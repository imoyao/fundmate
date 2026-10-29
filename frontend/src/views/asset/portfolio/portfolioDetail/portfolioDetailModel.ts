/**
 * 组合详情页的纯函数层（#980 拆分自 views/asset/portfolio/detail.vue）。
 *
 * 收口三件事：接口信封解包、持仓排序/分页、区间超额（#2134）的文案与配色。
 * 全是「输入 → 输出」，不碰响应式，便于直接喂数据断言。
 */

import type { LedgerItem } from "@/api/ledger";

/** 组合持仓（后端 /api/portfolios/{id}/holdings/ 返回，字段按现有代码使用为准） */
export interface PortfolioHolding {
  symbol?: string;
  name?: string | null;
  type_label?: string;
  market_value?: number;
  pnl?: number;
  pnl_rate?: number;
  account_name?: string;
  source?: string | null;
  /**
   * #1104：盈亏双线要用到的最小字段集（后端本就下发，此前页面类型没声明）。
   *
   * 注意 `type` 与 `quantity` 对**资产行**（`api/portfolio.ts` 注释：资产行 id = asset.id
   * + 100000）是空的——`confirmedPnl` 会返回 `null` 显示 `--`，这是正确行为：
   * 那些行没有「份额 × 现价」的口径，不该硬凑一个 0 出来。
   */
  type?: string | null;
  quantity?: number | null;
  current_price?: number | null;
  avg_price?: number | null;
  /** 价格时点（#2140 / #2210）：后端行级 price_date，部分路径缺省为 null */
  price_date?: string | null;
  /**
   * 当日确认口径是否已定型（#2210）：true = 估值副行应隐藏；null / 缺省 = 不隐藏。
   * **状态 = 后端字段契约**，前端禁止拿 price_date 自己跟今天比对推断。
   */
  settled_today?: boolean | null;
  /**
   * 归属方式（D20 二期 UI，**只读**）。
   *
   * 组合持仓有两条来源路径（`portfolio_service.portfolio_position_conditions`）：
   * - 显式指派：`portfolio_id` 等于本组合 id；
   * - 账户继承：`portfolio_id` 为 `null`，靠所属账户的默认组合带进来。
   *
   * **`undefined` ≠ `null`**：资产行（现金，id = asset.id + 100000）压根不带这个字段
   * （现金沿用账户归属，没有持仓级组合概念），必须与「继承态」分开判断——
   * 否则每一条现金都会被错标成「随账户」。
   */
  portfolio_id?: number | null;
}

/** 关联账户：账户 + 组合关联字段 */
export interface LinkedLedger extends LedgerItem {
  portfolio_id?: number | null;
}

/** 从接口信封（{ data, message } 或 { data: { data, message } }）中安全取出列表 */
export function unwrapList<T>(res: unknown): T[] {
  const d = (res as { data?: unknown })?.data;
  if (Array.isArray(d)) return d as T[];
  const nested = (d as { data?: unknown })?.data;
  return Array.isArray(nested) ? (nested as T[]) : [];
}

/**
 * 持仓排序。
 *
 * 无排序字段时**返回原序**（后端下发顺序，通常按市值降序），不在这里另立默认；
 * 排序键统一 `Number(... ?? 0)`——持仓行里 `pnl` / `pnl_rate` 对资产行是空值，
 * 不兜 0 会让 `undefined` 参与比较得到 NaN，整表顺序变随机。
 */
export function sortHoldings(
  holdings: PortfolioHolding[],
  prop: string | null,
  order: "ascending" | "descending" | null
): PortfolioHolding[] {
  if (!prop || !order) return [...holdings];
  const sorted = [...holdings];
  sorted.sort((a, b) => {
    const key = prop as keyof PortfolioHolding;
    const valA = Number(a[key] ?? 0);
    const valB = Number(b[key] ?? 0);
    return order === "ascending" ? valA - valB : valB - valA;
  });
  return sorted;
}

/** 前端分页切片（页码从 1 开始） */
export function slicePage<T>(list: T[], page: number, pageSize: number): T[] {
  const start = (page - 1) * pageSize;
  return list.slice(start, start + pageSize);
}

/** 账户类型中文名 */
export function ledgerTypeLabel(type: string): string {
  if (type === "cash") return "现金账户";
  if (type === "family") return "家庭账户";
  return "通用账户";
}

// #2595：超额五段派生（benchmarkLabelOf / benchmarkCaptionOf / excessValueText /
// excessColorOf / excessCaptionOf）上移到 `utils/benchmarkExcess.ts`（容器无关，
// 持仓分析聚合页共用）；此处 re-export 维持既有 import 与测试不变。
export {
  benchmarkLabelOf,
  benchmarkCaptionOf,
  excessValueText,
  excessColorOf,
  excessCaptionOf
} from "@/utils/benchmarkExcess";
