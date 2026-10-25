// 关联 ETF 对比表（#2275 / #2333 / #2334）的**纯函数层**（#980 拆分）。
//
// 为什么抽出来：九个格式化函数 + 两个「渲染门禁」判定原本全在组件里，改一列口径要在
// 模板、脚本、注释三处对齐；抽成具名纯函数后，「— 的降级边界」「优选 Top3 的截断」
// 「基准行要不要画」这些**降级契约**有单测兜底——这些正是第三方数据最容易静默漂移的地方。

import { productRoute } from "@/utils/productIdentity";
import type {
  IndexEtfCompareResult,
  IndexEtfCompareRow,
  IndexEtfCompareWindows
} from "@/api/products";

/** 缺失统一占位：任一字段失败 → 「—」，不阻塞整表 */
export const DASH = "—";

/** 收益窗口（顺序即列顺序） */
export const WINDOWS = [
  { key: "m1", label: "近1月" },
  { key: "m3", label: "近3月" },
  { key: "m6", label: "近6月" },
  { key: "y1", label: "近1年" }
] as const;

/** 跟踪差口径警示：非严格跟踪误差，title 必须带（表内与优选小卡同源复用） */
export const TRACKING_TITLE =
  "ETF 近 1 年涨幅 − 指数近 1 年涨幅；含折溢价噪声，非严格跟踪误差，仅作贴合度参考";

export const SCALE_TITLE =
  "基金规模 = 交易所份额 × 净值（深市源自带净值，沪市复用净值列）；交易所源不可用时以腾讯行情市价口径兜底，可能与资产净值有小幅偏差";

export const FEE_TITLE =
  "运作费率（%/年）：管理费率 / 托管费率，来自东财 F10 与同花顺，双源失败沿用最近 30 天内缓存";

/** 优选小卡的一行（展示用，已把 code → 路由算好） */
export interface EtfPick {
  code: string;
  name: string | null;
  rank: number;
  tracking: number | null;
  /** 空串 = 该品类没有详情页路由，退化成只读卡片 */
  route: string;
}

/**
 * 优选行：参评行按名次升序、至多 3 只。
 *
 * 后端契约本就是「门槛内 Top3」，这里的 `slice(0, 3)` 是防御——后端多给也不画第四张卡
 * （卡位是 `auto-fit` 网格，多一张会把布局挤成两行参差）。
 */
export function recommendRowsOf(rows: IndexEtfCompareRow[]): EtfPick[] {
  return rows
    .filter(
      (row): row is IndexEtfCompareRow & { recommend_rank: number } =>
        row.recommend_rank != null
    )
    .sort((a, b) => a.recommend_rank - b.recommend_rank)
    .slice(0, 3)
    .map(row => ({
      code: row.code,
      name: row.name,
      rank: row.recommend_rank,
      tracking: row.tracking_diff_y1,
      route: productRoute({ assetType: "etf", symbol: row.code })
    }));
}

/** 名次称谓：第 1 名带「优选」前缀突出，2/3 名只标名次 */
export function recommendLabel(rank: number): string {
  return rank === 1 ? "优选 · 第 1" : `第 ${rank}`;
}

/**
 * 指数基准行：任一窗口有值才渲染。
 *
 * 全 null 时画一行「—」没有信息量（反而像「指数收益为 0」），故整行不画。
 */
export function indexBaselineOf(
  data: IndexEtfCompareResult | null
): IndexEtfCompareWindows | null {
  const w = data?.index_returns;
  if (!w) return null;
  return WINDOWS.some(x => w[x.key] != null) ? w : null;
}

/** 脚注：净值口径（T-1）+ 行情来源，缺 `as_of` 时只说来源 */
export function footnoteOf(data: IndexEtfCompareResult | null): string {
  if (!data) return "";
  const navPart = data.as_of ? `净值截至 ${data.as_of}（T-1 口径）` : "";
  const spotPart = "当日行情来自新浪财经";
  return [navPart, spotPart].filter(Boolean).join(" · ");
}

/** 收益率文本：null → 「—」；正数补 `+`（0 不补，避免读成「上涨 0」以外的歧义） */
export function pctText(value: number | null): string {
  return value == null ? DASH : `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

/** 涨跌语义类（红涨绿跌由令牌给，这里只判正负） */
export function pctClass(value: number | null): Record<string, boolean> {
  return {
    "etf-cmp__num--rise": value != null && value > 0,
    "etf-cmp__num--fall": value != null && value < 0
  };
}

/** 最新净值：4 位小数（场内 ETF 净值精度，与基金净值同纪律） */
export function navText(row: IndexEtfCompareRow): string {
  return row.nav == null ? DASH : row.nav.toFixed(4);
}

/** 成交额：元 → 亿 / 万（两档够用，ETF 成交额量级大） */
export function amountText(row: IndexEtfCompareRow): string {
  const amount = row.amount;
  if (amount == null) return DASH;
  if (amount >= 1e8) return `${(amount / 1e8).toFixed(2)}亿`;
  if (amount >= 1e4) return `${(amount / 1e4).toFixed(1)}万`;
  return amount.toFixed(0);
}

/** 跟踪差文本（与 `pctText` 同形，但口径不同，分开命名以免误改一处影响另一处） */
export function trackingText(value: number | null): string {
  return value == null ? DASH : `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

/** 规模（#2333）：后端已给亿元 */
export function scaleText(row: IndexEtfCompareRow): string {
  return row.scale_yi == null ? DASH : `${row.scale_yi.toFixed(2)}亿`;
}

/**
 * 费率（#2333）：管理费 / 托管费（%/年）。
 *
 * 单缺只显不缺的那只（`管理 0.50%`），双缺才「—」——只缺托管费时整格变「—」
 * 会让人以为管理费也没抓到。
 */
export function feeText(row: IndexEtfCompareRow): string {
  const mgmt = row.mgmt_fee_pct;
  const custody = row.custody_fee_pct;
  if (mgmt == null && custody == null) return DASH;
  const parts = [
    mgmt == null ? null : `管理 ${mgmt.toFixed(2)}%`,
    custody == null ? null : `托管 ${custody.toFixed(2)}%`
  ].filter((x): x is string => x != null);
  return parts.join(" / ");
}

/** 代码 → ETF 详情路由（空串表示一期不开放，表内退化成纯文本） */
export function etfRouteOf(code: string): string {
  return productRoute({ assetType: "etf", symbol: code });
}
