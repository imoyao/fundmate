// frontend/src/utils/__tests__/externalLinks.spec.ts
import { describe, expect, it } from "vitest";
import { externalQuoteLinks, splitSymbolForLinks } from "../externalLinks";

const urlsOf = (links: { url: string }[]) => links.map(l => l.url);
const labelsOf = (links: { label: string }[]) => links.map(l => l.label);

describe("splitSymbolForLinks", () => {
  it("拆出交易所前缀与裸码（内部形态 → 各家要的形态）", () => {
    expect(splitSymbolForLinks("SH601899")).toEqual({
      prefix: "SH",
      bare: "601899"
    });
    expect(splitSymbolForLinks("sz000001")).toEqual({
      prefix: "SZ",
      bare: "000001"
    });
    expect(splitSymbolForLinks("US:AAPL")).toEqual({
      prefix: "US",
      bare: "AAPL"
    });
    expect(splitSymbolForLinks("OF.004369")).toEqual({
      prefix: "",
      bare: "004369"
    });
    expect(splitSymbolForLinks("004369")).toEqual({ prefix: "", bare: "004369" });
    expect(splitSymbolForLinks("  ")).toEqual({ prefix: "", bare: "" });
  });
});

describe("externalQuoteLinks", () => {
  it("A 股给四家，且各自用对形态（同花顺裸码 / 东财小写 / 雪球带前缀）", () => {
    const links = externalQuoteLinks({ symbol: "SH601899", assetType: "stock" });

    expect(labelsOf(links)).toEqual([
      "同花顺",
      "东方财富",
      "雪球",
      "新浪财经"
    ]);
    expect(urlsOf(links)).toEqual([
      "http://stockpage.10jqka.com.cn/601899/",
      "https://quote.eastmoney.com/sh601899.html",
      "https://xueqiu.com/S/SH601899",
      "https://finance.sina.com.cn/realstock/company/sh601899/nc.shtml"
    ]);
  });

  it("深市用小写 sz（东财 / 新浪同形态）", () => {
    const urls = urlsOf(
      externalQuoteLinks({ symbol: "SZ000001", assetType: "stock" })
    );

    expect(urls).toContain("https://quote.eastmoney.com/sz000001.html");
    expect(urls).toContain("https://xueqiu.com/S/SZ000001");
  });

  it("ETF 与股票同规则（场内同形态）", () => {
    const links = externalQuoteLinks({ symbol: "SH513130", assetType: "etf" });

    expect(links).toHaveLength(4);
  });

  it("北交所只给形态确定的平台（这两家对 BJ 的页面形态未实测）", () => {
    const labels = labelsOf(
      externalQuoteLinks({ symbol: "BJ830799", assetType: "stock" })
    );

    expect(labels).toEqual(["东方财富", "雪球"]);
  });

  it("港股：雪球用裸 5 位码，东财用 hk 前缀", () => {
    const urls = urlsOf(
      externalQuoteLinks({ symbol: "HK00700", assetType: "stock" })
    );

    expect(urls).toEqual([
      "https://quote.eastmoney.com/hk/00700.html",
      "https://xueqiu.com/S/00700"
    ]);
  });

  it("美股：雪球用 ticker，东财用 us 前缀", () => {
    const urls = urlsOf(
      externalQuoteLinks({ symbol: "US:AAPL", assetType: "stock" })
    );

    expect(urls).toEqual([
      "https://quote.eastmoney.com/us/AAPL.html",
      "https://xueqiu.com/S/AAPL"
    ]);
  });

  it("场外基金走基金站点（与股票完全不同，且都吃 6 位裸码）", () => {
    const urls = urlsOf(
      externalQuoteLinks({ symbol: "004369", assetType: "fund" })
    );

    expect(urls).toEqual([
      "https://fund.eastmoney.com/004369.html",
      "http://fund.10jqka.com.cn/004369/",
      "https://qieman.com/funds/004369"
    ]);
  });

  it("`OF.` 形态要剥掉前缀（接口入参的历史约定）", () => {
    const urls = urlsOf(
      externalQuoteLinks({ symbol: "OF.004369", assetType: "fund" })
    );

    expect(urls[0]).toBe("https://fund.eastmoney.com/004369.html");
  });

  it("货基与场外基金同站点", () => {
    expect(
      externalQuoteLinks({ symbol: "000198", assetType: "money_fund" })
    ).toHaveLength(3);
  });

  it("可转债走东财数据中心（股票形态的 quote 页对它返回 404）", () => {
    const urls = urlsOf(
      externalQuoteLinks({ symbol: "SH113050", assetType: "bond" })
    );

    expect(urls).toEqual([
      "https://data.eastmoney.com/kzz/detail/113050.html"
    ]);
  });

  it("指数走东财 zs 前缀", () => {
    const urls = urlsOf(
      externalQuoteLinks({ symbol: "SH000300", assetType: "index" })
    );

    expect(urls).toEqual(["https://quote.eastmoney.com/zs000300.html"]);
  });

  it("没有对应站点的品类返回空数组（不硬凑一个财经首页）", () => {
    expect(
      externalQuoteLinks({ symbol: "MGR_001", assetType: "manager" })
    ).toEqual([]);
    expect(
      externalQuoteLinks({ symbol: "ZH0001", assetType: "portfolio" })
    ).toEqual([]);
    expect(
      externalQuoteLinks({ symbol: "BTC-USD", assetType: "crypto" })
    ).toEqual([]);
  });

  it("空 symbol 返回空数组", () => {
    expect(externalQuoteLinks({ symbol: "   ", assetType: "stock" })).toEqual(
      []
    );
  });
});
