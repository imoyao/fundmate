// frontend/src/api/products/indices.ts
// 指数资料 / 阶段收益 / 十大权重 / ETF 对比（#2878 子域拆分；实现逐字搬自 api/products.ts，端点契约勿改）
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/**
 * 指数资料聚合结果（#2028 · `/api/products/index-profile/`）。
 *
 * 字段缺失一律 null，前端降级「—」。分位是**读路径现算**（乐咕月频近 5 年窗口，
 * #1407 拍板）：样本不足 12 点时 pe_percentile 为 null——那是「样本不够」不是
 * 「分位为 0」，两者语义相反，不可混。股息率分位本期恒为 null（乐咕无该序列）。
 *
 * 唯一例外是 `description`（指数简介散文）：null 时前端**整段隐藏**而非显示「—」——
 * 没有简介是「官网未收录」（399 系等），摆一个破折号占位反而像数据出错。
 */
export interface IndexProfileResult {
  /** 裸 6 位指数码（service 已归一，带前缀入口也返回裸码） */
  index_code: string;
  /** 指数中文简称（index_catalog.name） */
  name: string;
  /** 编制/发布机构中文名（中证指数公司 / 国证指数…）；未知为 null */
  publisher_label: string | null;
  /** 核心指数白名单标记（自选分组置顶用，此处仅展示「核心」徽标） */
  is_core: boolean;
  /** 指数简介原文（中证官网 indexCnDesc，后端按需抓取+进程内缓存）；官网未收录（399 系等）或抓取失败为 null——整段隐藏，不显示「—」 */
  description: string | null;
  /** 市盈率（中证官方口径 pe_1，最新一期）；无官方估值文件为 null */
  pe: number | null;
  /** 股息率(%)（中证官方口径 dividend_yield_1）；为 null 时不可显示为 0 */
  dividend_yield: number | null;
  /** 估值日期 YYYY-MM-DD（官方文件最新一期） */
  valuation_date: string | null;
  /** PE 历史分位(%)：乐咕滚动 PE 在近 5 年月频窗口中的位置；样本不足为 null */
  pe_percentile: number | null;
  /** 分位口径元数据（脚注直接展示，前端不另建映射） */
  percentile_metric: string | null;
  /** 分位基线的最新采样日 YYYY-MM-DD */
  percentile_date: string | null;
  /** 发布日期（中证官网 publishDate）；官网未填为 null → 显示「—」（#2278） */
  publish_date: string | null;
  /** 样本数（consNumber）；官网未填为 null → 显示「—」 */
  cons_number: number | null;
  /** 加权方式（weightingType，如「自由流通市值加权」）；官网未填为 null → 显示「—」 */
  weighting_type: string | null;
  /** 币种（currencyCn，如「人民币」）；官网未填为 null → 显示「—」 */
  currency: string | null;
}

/** 取指数资料聚合。404 = 该代码不在指数名录。 */
export function getIndexProfile(symbol: string) {
  return http.request<ApiResponse<IndexProfileResult>>(
    "get",
    "/api/products/index-profile/",
    { params: { symbol } }
  );
}

/** 阶段性收益窗口键 → 结果值映射（%）；null = 历史不足该窗口，前端「—」（#2278） */
export interface IndexReturnsWindows {
  m1: number | null;
  m3: number | null;
  ytd: number | null;
  y1: number | null;
  y2: number | null;
  y3: number | null;
}

/** 指数阶段性收益 + 年化波动率（`/api/products/index-returns/`，#2278）。
 * 数据按需抓自公开行情源（中证官网/腾讯），服务端现算即弃、不入库；两路全空时
 * `as_of`/`source` 为 null 且窗口全 null，前端整块降级，不阻塞页面其余区块。 */
export interface IndexReturnsResult {
  index_code: string;
  /** 最后交易日 YYYY-MM-DD；无数据为 null */
  as_of: string | null;
  /** 数据来源：csindex=中证指数官网 / tencent=腾讯行情；无数据为 null */
  source: string | null;
  returns: IndexReturnsWindows;
  /** 近 1 年年化波动率(%)：日频收益样本标准差 × √252；历史不足 1 年为 null */
  volatility_y1: number | null;
}

export function fetchIndexReturns(symbol: string) {
  return http.request<ApiResponse<IndexReturnsResult>>(
    "get",
    "/api/products/index-returns/",
    { params: { symbol } }
  );
}

/** 十大权重单行（月频口径）；weight 为 %，保留源侧 3 位小数 */
export interface IndexWeightRow {
  code: string;
  name: string;
  weight: number;
  exchange: string | null;
}

/** 指数十大权重 + 前十大集中度（`/api/products/index-weights/`，#2278）。
 * 源 = 中证权重接口（月频）优先，口径不覆盖时回退国证官网；接口失败/两路都不
 * 覆盖 → `top10: []` 且其余字段 null，前端整块降级「—」。 */
export interface IndexWeightsResult {
  index_code: string;
  /** 权重数据日期 YYYY-MM-DD（月频，须在前端标注口径）；无数据为 null */
  as_of: string | null;
  frequency: string;
  /** 权重来源（口径标注用）：`csindex` 中证 / `cni` 国证 / null 无数据 */
  source: string | null;
  /** 成分股总数（如光伏产业 50 只） */
  constituent_count: number;
  total_weight: number | null;
  /** 前十大权重合计（%），集中度一眼可见 */
  top10_weight: number | null;
  top10: IndexWeightRow[];
}

export function fetchIndexWeights(symbol: string) {
  return http.request<ApiResponse<IndexWeightsResult>>(
    "get",
    "/api/products/index-weights/",
    { params: { symbol } }
  );
}

/** 关联 ETF 对比表窗口收益（#2275）：近 1/3/6/12 月（%）；null = 历史不足 */
export interface IndexEtfCompareWindows {
  m1: number | null;
  m3: number | null;
  m6: number | null;
  y1: number | null;
}

/** 关联 ETF 对比表单行（#2275 · P0）。所有行情字段缺失一律 null，前端降级「—」 */
export interface IndexEtfCompareRow {
  code: string;
  name: string | null;
  /** 最新单位净值（止于 T-1）；快照源失败为 null */
  nav: number | null;
  /** 净值日期 YYYY-MM-DD */
  nav_date: string | null;
  /** 净值日增长率(%) */
  nav_change_pct: number | null;
  /** 当日涨跌幅(%)（新浪现货快照） */
  change_pct: number | null;
  /** 当日成交额（元） */
  amount: number | null;
  returns: IndexEtfCompareWindows;
  /** 跟踪差(%) = ETF 近 1 年涨幅 − 指数近 1 年涨幅；任一侧缺失为 null */
  tracking_diff_y1: number | null;
  /** 基金规模(亿元，#2333)：交易所份额×净值，腾讯市价口径兜底；失败为 null */
  scale_yi: number | null;
  /** 管理费率(%/年，#2333)：东财 F10 / 同花顺双源 + 小表旧值；失败为 null */
  mgmt_fee_pct: number | null;
  /** 托管费率(%/年，#2333)；失败为 null */
  custody_fee_pct: number | null;
  /** 优选排名(#2334)：1~3 = 进入优选小卡的名次（参评门槛内按跟踪差降序）；不参评为 null */
  recommend_rank: number | null;
}

/**
 * 指数详情页关联 ETF 对比表（`/api/products/index-etf-compare/`，#2275）。
 * ETF 清单来自本地 channel_links（覆盖率约 66.4%，#1419）；`rows: []` 表示
 * 无关联 ETF（正常情形），整表隐藏。数据按需抓 + 30min 缓存，任一字段失败
 * 不阻塞整表。
 */
export interface IndexEtfCompareResult {
  index_code: string;
  /** 共同最新交易日 = 指数序列最新日 与 ETF 侧最新日的较小者；双侧全缺为 null */
  as_of: string | null;
  /** 指数自身四窗口收益（对比表基准行数据源；任一窗口缺失为 null） */
  index_returns?: IndexEtfCompareWindows;
  rows: IndexEtfCompareRow[];
}

export function fetchIndexEtfCompare(symbol: string) {
  return http.request<ApiResponse<IndexEtfCompareResult>>(
    "get",
    "/api/products/index-etf-compare/",
    { params: { symbol } }
  );
}
