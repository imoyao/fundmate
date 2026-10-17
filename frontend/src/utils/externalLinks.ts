// frontend/src/utils/externalLinks.ts
/**
 * 第三方行情 / 资料站外链（#1969 · 详情页「更多数据」区块）。
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
 * - 已验证（内容随代码变化）：同花顺 / 东方财富（A股·港股·美股·可转债；指数为
 *   `zz/{市场码}.{代码}.html`，2026-10-16 按有效/无效代码对比实测——旧 `zs` 形态
 *   对 9 系已 404）/ 新浪财经 / 天天基金 / 爱基金 / 且慢
 * - 雪球是 SPA，服务端对任意代码返回同一壳页，**无法离线验证**；股票/ETF 按其公开的
 *   标准形态拼（`/S/` + 交易所前缀），拼错时雪球自己会提示「未找到」。**指数前缀已
 *   浏览器实测页面标题**（2026-10-16：0→SH、399→SZ、899→BJ、9 系→CSI）。
 * - 中证官网指数页是 SPA hash 路由（`#/indices/family/detail?indexCode=`），服务端对
 *   任意代码返回同一壳页，离线同样无法验证；收录范围按 `csindex-home/indexInfo/
 *   index-basic-info/{code}` 实测（0/9/899/H/L 系有收录，399/4/CES/B/8 位 98 系
 *   返回 data=null）——不在覆盖码族内**不生成链接**（点进去是空页不如不给）。
 * - **不放晨星中国**：它的基金页要 Morningstar 内部 SecId（`0P0000xxxx`），且
 *   `fund/search.aspx` 实测忽略一切查询参数（换 4 个参数名都返回同一只基金），
 *   用基金代码拼不出正确页面。
 * - **不放集思录**：见上，无法确认按代码可达。
 *
 * ## 可转债**不归本模块**（踩过一次重复实现的坑）
 *
 * 可转债有自己的 `utils/bondExternalLinks.ts` + `BondExternalLinkCard`（#1971：集思录
 * 条款数据 + 登录墙提示 + 游客降级入口），详情页对 `bond` 品类渲染那张卡。
 * 本模块此处曾同时给转债出链（东财数据中心页），合并后详情页一度**出现两块外链卡**。
 * 故 `bond` 在此返回空数组 —— 新增品类时先确认「是否已有专用卡」，别再叠一层。
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

  // ── 指数：中证官网（首位）→ 东财 zz → 雪球（前缀按码族）──
  if (type === "index") {
    // 入参可能是裸码（931151）或带前缀（SH000300）；中证/雪球内部的 CSI 前缀
    // 不在 splitSymbolForLinks 的拆分范围，手动剥掉
    const code = bare.replace(/^CSI/, "");
    const links: ExternalLink[] = [];

    // ① 中证官网详情页（SPA hash 路由，用户指定形态）——放首位。
    // 覆盖判据（2026-10-16 实测 csindex-home/indexInfo/index-basic-info/{code}）：
    // 0 系 / 9 系(6 位) / 899 / H / L 系有收录；399 系、4 系(CNH)、CES/B 系、
    // 8 位 98 系返回 data=null——官网点进去是空页，按本模块「宁可不给」原则不生成
    if (/^(?:[089]\d{5}|H\d+|L\d+)$/.test(code)) {
      links.push({
        key: "csindex",
        label: "中证官网",
        url: `https://www.csindex.com.cn/#/indices/family/detail?indexCode=${code}`
      });
    }

    // ② 东财：zz/{市场码}.{代码}.html。市场码按裸码首位数字（2026-10-16 有效/
    // 无效代码对比实测）：0→1（上证）、3/4/8→0（深证/北证/CNH）、9→2（中证）；
    // 旧 zs/ 形态对 9 系已 404，统一改 zz
    const EM_MARKET: Record<string, string> = {
      "0": "1",
      "3": "0",
      "4": "0",
      "8": "0",
      "9": "2"
    };
    if (/^\d{6}$/.test(code) && EM_MARKET[code[0]]) {
      links.push({
        key: "eastmoney-index",
        label: "东方财富",
        url: `https://quote.eastmoney.com/zz/${EM_MARKET[code[0]]}.${code}.html`
      });
    }

    // ③ 雪球 /S/{前缀}{码}：指数前缀按码族（2026-10-16 浏览器实测页面标题：
    //   0→SH、399→SZ、899→BJ、9 系→CSI，均逐一核对标题正确）；其余码族
    //   未实测 → 不给（拼错雪球只会回「未找到」，不如不放）
    const xqPrefix =
      code[0] === "9"
        ? "CSI"
        : code.startsWith("399")
          ? "SZ"
          : code.startsWith("899")
            ? "BJ"
            : code[0] === "0"
              ? "SH"
              : "";
    if (xqPrefix && /^\d{6}$/.test(code)) {
      links.push({
        key: "xueqiu",
        label: "雪球",
        url: `https://xueqiu.com/S/${xqPrefix}${code}`
      });
    }

    return links;
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
      {
        key: "xueqiu",
        label: "雪球",
        url: `https://xueqiu.com/S/${prefix}${bare}`
      },
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
    return [
      { key: "xueqiu", label: "雪球", url: `https://xueqiu.com/S/${bare}` }
    ];
  }
  return [];
}
