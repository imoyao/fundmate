// frontend/src/utils/externalLinks.ts
/**
 * 第三方行情 / 资料站外链（#1969 · 详情页「第三方数据」区块）。
 *
 * 存在理由：我们的数据完整度受限于抓取链路（且不该把自己做成行情终端），
 * 深度研究交给专业站更合理 —— 用户想知道「这只票的资金流 / 五档 / 财务」时，
 * 与其等我们补数据，不如直接送他过去。
 *
 * ## 形态转换集中在此（唯一一处）
 *
 * 内部 symbol 是一套形态（`SH601899` / `HK00700` / `US:AAPL` / 场外裸码 `004369`），
 * 各家站点要的是另一套（同花顺要裸码、东财要小写前缀、雪球要带交易所前缀）。
 * 转换只在这里做一次，任何页面都不得自己拼字符串跳转。
 *
 * ## 平台可用性是**实测**出来的，不是照抄网上的 URL 模板
 *
 * 验证方法：抓「有效代码」与「不存在的代码」两个页面，比较 HTML 长度 / 标题是否
 * 随代码变化。只测状态码是不够的 —— SPA 壳页与登录墙对任何代码都返回 200，
 * 真点进去才发现是空页（集思录就是这么被否掉的：两个 URL 返回**同一个 1410 字节
 * 壳页**）。
 *
 * - 已验证（内容随代码变化）：同花顺 / 东方财富（A股·港股·美股·指数·可转债）/
 *   新浪财经 / 天天基金 / 爱基金 / 且慢
 * - 雪球是 SPA，服务端对任意代码返回同一壳页，**无法离线验证**；此处按其公开的
 *   标准形态拼（`/S/` + 交易所前缀），拼错时雪球自己会提示「未找到」。
 * - **不放晨星中国**：它的基金页要 Morningstar 内部 SecId（`0P0000xxxx`），且
 *   `fund/search.aspx` 实测忽略一切查询参数（换 4 个参数名都返回同一只基金），
 *   用基金代码拼不出正确页面。
 * - **不放集思录**：见上，无法确认按代码可达。
 */

/** 一条外链。`label` 是站点名（面向用户），`key` 供前端做稳定性标识 */
export interface ExternalLink {
  key: string;
  label: string;
  url: string;
}

/** 外链入参：详情页 resolve 之后拿到的事实 */
export interface ExternalLinkInput {
  symbol: string;
  /** 后端判定的品类（stock / etf / bond / fund / money_fund / index…） */
  assetType?: string | null;
  /** 契约市场（CN_A / CN_HK / US / CRYPTO…），仅用于兜底判断 */
  market?: string | null;
}

interface SymbolParts {
  /** 交易所前缀：SH / SZ / BJ / HK / US；场外与未知形态为空串 */
  prefix: string;
  /** 去掉前缀的代码本体 */
  bare: string;
}

/** 内部 symbol → 交易所前缀 + 裸码 */
export function splitSymbolForLinks(symbol: string): SymbolParts {
  const s = (symbol || "").trim().toUpperCase();
  if (!s) return { prefix: "", bare: "" };
  // 美股：内部归一形态是 `US:AAPL`（见后端 symbol_utils._build_normalized）
  if (s.startsWith("US:")) return { prefix: "US", bare: s.slice(3) };
  // 场外基金：接口入参的历史约定形态是 `OF.004369`（入库侧是裸码）
  if (s.startsWith("OF.")) return { prefix: "", bare: s.slice(3) };
  const matched = /^(SH|SZ|BJ|HK|CR)(.+)$/.exec(s);
  if (matched) return { prefix: matched[1], bare: matched[2] };
  return { prefix: "", bare: s };
}

/**
 * 生成该产品的第三方外链列表。
 *
 * 品类没有对应站点时返回**空数组**（如基金经理、投顾组合、加密货币）——
 * 不硬凑一个「财经首页」，那对用户没有增量价值。
 */
export function externalQuoteLinks(input: ExternalLinkInput): ExternalLink[] {
  const type = (input.assetType || "").trim().toLowerCase();
  const { prefix, bare } = splitSymbolForLinks(input.symbol);
  if (!bare) return [];

  // ── 场外基金 / 货基：站点与股票完全不同，且都吃 6 位裸码 ──
  if (type === "fund" || type === "money_fund") {
    return [
      {
        key: "eastmoney-fund",
        label: "天天基金",
        url: `https://fund.eastmoney.com/${bare}.html`
      },
      {
        key: "aijijin",
        label: "爱基金",
        url: `http://fund.10jqka.com.cn/${bare}/`
      },
      { key: "qieman", label: "且慢", url: `https://qieman.com/funds/${bare}` }
    ];
  }

  // ── 可转债：东财数据中心有独立详情页（股票形态的 quote 页对它 404）──
  if (type === "bond") {
    return [
      {
        key: "eastmoney-cb",
        label: "东方财富",
        url: `https://data.eastmoney.com/kzz/detail/${bare}.html`
      }
    ];
  }

  // ── 指数：东财用 `zs` 前缀 ──
  if (type === "index") {
    return [
      {
        key: "eastmoney-index",
        label: "东方财富",
        url: `https://quote.eastmoney.com/zs${bare}.html`
      }
    ];
  }

  // ── 场内交易品种：股票 / ETF（可转债已在上方单独处理）──
  if (type !== "stock" && type !== "etf") return [];

  if (prefix === "HK") {
    return [
      {
        key: "eastmoney",
        label: "东方财富",
        url: `https://quote.eastmoney.com/hk/${bare}.html`
      },
      { key: "xueqiu", label: "雪球", url: `https://xueqiu.com/S/${bare}` }
    ];
  }

  if (prefix === "US") {
    return [
      {
        key: "eastmoney",
        label: "东方财富",
        url: `https://quote.eastmoney.com/us/${bare}.html`
      },
      { key: "xueqiu", label: "雪球", url: `https://xueqiu.com/S/${bare}` }
    ];
  }

  if (prefix === "SH" || prefix === "SZ" || prefix === "BJ") {
    const lower = prefix.toLowerCase();
    // 同花顺与新浪只对沪 / 深两市给：北交所（BJ）在这两家的页面形态**未实测**，
    // 宁可不给，也不放一条点进去是空页的链接
    const isHuShen = prefix === "SH" || prefix === "SZ";
    return [
      ...(isHuShen
        ? [
            {
              key: "ths",
              label: "同花顺",
              url: `http://stockpage.10jqka.com.cn/${bare}/`
            }
          ]
        : []),
      {
        key: "eastmoney",
        label: "东方财富",
        url: `https://quote.eastmoney.com/${lower}${bare}.html`
      },
      { key: "xueqiu", label: "雪球", url: `https://xueqiu.com/S/${prefix}${bare}` },
      ...(isHuShen
        ? [
            {
              key: "sina",
              label: "新浪财经",
              url: `https://finance.sina.com.cn/realstock/company/${lower}${bare}/nc.shtml`
            }
          ]
        : [])
    ];
  }

  // 无前缀（形态不明）→ 只有雪球能用裸码兜一把，且仅限 A 股 6 位码
  if (/^\d{6}$/.test(bare)) {
    return [{ key: "xueqiu", label: "雪球", url: `https://xueqiu.com/S/${bare}` }];
  }
  return [];
}
