/**
 * 指数目录（#watchlist 指数条个性化设置的可选项池）。
 *
 * 码表均经 `qt.gtimg.cn` 实跑验证（2026-11-03）：行情（点位 + 涨跌幅）对每个条目都返回有效数据。
 * 分时（东财 push2his）分两档：
 *   - `intradayReliable=true`：A 股 `1./0.` secid 稳定可取；
 *   - `intradayReliable=false`：港股/美股 secid 为 best-effort（`100.XXX`），
 *     取数失败仅缺分时折线、不影响行情与涨跌（见 IndexMarketBar 的降级处理）。
 *
 * 故意排除的 7 个国际指数（富时100 / CAC40 / 德国DAX真实指数 / 日经225 / 东证指数 /
 * 韩国综合 / 韩国创业板）：腾讯 gtimg 无任何对应指数码（DAX 仅 `usDAX` 这个 ETF 代理，
 * 价 ~44 不是指数点位）。待接入其它数据源后再补，避免配置页出现取不到数据的空卡。
 *
 * `detailSymbol` 沿用 IndexMarketBar 原有格式（`<EX><CODE>`），供 productRoute
 * （assetType=index）跳详情页。
 */

export type IndexMarketGroup = "CN" | "HK" | "US";

export interface IndexCatalogEntry {
  /** 稳定 id（也是 localforage 持久化与排序的键） */
  key: string;
  name: string;
  /** 腾讯行情外部码（fetchTencentIndexQuotes 直接吃） */
  tencentCode: string;
  /** 东财分时 secid（fetchIntradayTrendBySecid） */
  secid: string;
  /** 详情页内部 symbol（assetType=index） */
  detailSymbol: string;
  group: IndexMarketGroup;
  /** 分时是否稳定可取（false = best-effort） */
  intradayReliable: boolean;
}

export const INDEX_CATALOG: IndexCatalogEntry[] = [
  // ── A 股（sh/sz/bj；行情 + 分时均稳） ──
  {
    key: "sh000001",
    name: "上证指数",
    tencentCode: "sh000001",
    secid: "1.000001",
    detailSymbol: "SH000001",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sh000016",
    name: "上证50",
    tencentCode: "sh000016",
    secid: "1.000016",
    detailSymbol: "SH000016",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sh000010",
    name: "上证180",
    tencentCode: "sh000010",
    secid: "1.000010",
    detailSymbol: "SH000010",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sz399001",
    name: "深证成指",
    tencentCode: "sz399001",
    secid: "0.399001",
    detailSymbol: "SZ399001",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sz399330",
    name: "深证100",
    tencentCode: "sz399330",
    secid: "0.399330",
    detailSymbol: "SZ399330",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sz399005",
    name: "中小100",
    tencentCode: "sz399005",
    secid: "0.399005",
    detailSymbol: "SZ399005",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sz399300",
    name: "沪深300",
    tencentCode: "sz399300",
    secid: "0.399300",
    detailSymbol: "SZ399300",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sh000905",
    name: "中证500",
    tencentCode: "sh000905",
    secid: "1.000905",
    detailSymbol: "SH000905",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sh000906",
    name: "中证800",
    tencentCode: "sh000906",
    secid: "1.000906",
    detailSymbol: "SH000906",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sh000852",
    name: "中证1000",
    tencentCode: "sh000852",
    secid: "1.000852",
    detailSymbol: "SH000852",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sh000903",
    name: "中证A100",
    tencentCode: "sh000903",
    secid: "1.000903",
    detailSymbol: "SH000903",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sh000904",
    name: "中证200",
    tencentCode: "sh000904",
    secid: "1.000904",
    detailSymbol: "SH000904",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sh000688",
    name: "科创50",
    tencentCode: "sh000688",
    secid: "1.000688",
    detailSymbol: "SH000688",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sz399006",
    name: "创业板指",
    tencentCode: "sz399006",
    secid: "0.399006",
    detailSymbol: "SZ399006",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sz399004",
    name: "创业板综",
    tencentCode: "sz399004",
    secid: "0.399004",
    detailSymbol: "SZ399004",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sz399673",
    name: "创业板50",
    tencentCode: "sz399673",
    secid: "0.399673",
    detailSymbol: "SZ399673",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sz399932",
    name: "中证消费",
    tencentCode: "sz399932",
    secid: "0.399932",
    detailSymbol: "SZ399932",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "sz399303",
    name: "国证2000",
    tencentCode: "sz399303",
    secid: "0.399303",
    detailSymbol: "SZ399303",
    group: "CN",
    intradayReliable: true
  },
  {
    key: "bj899050",
    name: "北证50",
    tencentCode: "bj899050",
    secid: "0.899050",
    detailSymbol: "BJ899050",
    group: "CN",
    intradayReliable: false
  },

  // ── 港股（行情稳；分时 best-effort） ──
  {
    key: "hkHSI",
    name: "恒生指数",
    tencentCode: "hkHSI",
    secid: "100.HSI",
    detailSymbol: "HKHSI",
    group: "HK",
    intradayReliable: false
  },
  {
    key: "hkHSTECH",
    name: "恒生科技",
    tencentCode: "hkHSTECH",
    secid: "100.HSTECH",
    detailSymbol: "HKHSTECH",
    group: "HK",
    intradayReliable: false
  },

  // ── 美股（行情稳；分时 best-effort；标普500 的码是 usINX 不是 usSPX） ──
  {
    key: "usIXIC",
    name: "纳斯达克",
    tencentCode: "usIXIC",
    secid: "100.IXIC",
    detailSymbol: "USIXIC",
    group: "US",
    intradayReliable: false
  },
  {
    key: "usDJI",
    name: "道琼斯",
    tencentCode: "usDJI",
    secid: "100.DJI",
    detailSymbol: "USDJI",
    group: "US",
    intradayReliable: false
  },
  {
    key: "usNDX",
    name: "纳斯达克100",
    tencentCode: "usNDX",
    secid: "100.NDX",
    detailSymbol: "USNDX",
    group: "US",
    intradayReliable: false
  },
  {
    key: "usINX",
    name: "标普500",
    tencentCode: "usINX",
    secid: "100.INX",
    detailSymbol: "USINX",
    group: "US",
    intradayReliable: false
  },
  {
    key: "usVIX",
    name: "标普500波动率",
    tencentCode: "usVIX",
    secid: "100.VIX",
    detailSymbol: "USVIX",
    group: "US",
    intradayReliable: false
  }
];

/** 默认选中（沿用 IndexMarketBar 上线时的 5 个） */
export const DEFAULT_INDEX_KEYS: string[] = [
  "sh000001",
  "sz399001",
  "sz399006",
  "hkHSI",
  "usIXIC"
];

export const INDEX_CATALOG_BY_KEY: Record<string, IndexCatalogEntry> =
  Object.fromEntries(INDEX_CATALOG.map(e => [e.key, e]));

/** 仅保留目录中存在的 key（过滤持久化脏数据） */
export function filterValidKeys(keys: string[]): string[] {
  return keys.filter(k => INDEX_CATALOG_BY_KEY[k]);
}
