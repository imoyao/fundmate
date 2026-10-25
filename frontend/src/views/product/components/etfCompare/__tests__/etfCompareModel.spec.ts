import { describe, expect, it } from "vitest";

import type { IndexEtfCompareRow } from "@/api/products";
import {
  DASH,
  WINDOWS,
  amountText,
  feeText,
  footnoteOf,
  indexBaselineOf,
  navText,
  pctClass,
  pctText,
  recommendLabel,
  recommendRowsOf,
  scaleText,
  trackingText
} from "../etfCompareModel";

/**
 * 关联 ETF 对比表的纯函数层（#980 拆分）。
 *
 * 重点钉的是**降级契约**：这张表的每一列都来自第三方（东财 F10 / 同花顺 / 新浪 /
 * 腾讯兜底），任一字段失败都得落到「—」而不是 `NaN` / `null` / `undefined`。
 * 第三方数据最容易静默漂移的正是这里，所以九条格式化逐个测「缺失 → —」。
 */

function row(over: Partial<IndexEtfCompareRow> = {}): IndexEtfCompareRow {
  return {
    code: "510300",
    name: "沪深300ETF",
    nav: null,
    nav_date: null,
    nav_change_pct: null,
    change_pct: null,
    amount: null,
    returns: { m1: null, m3: null, m6: null, y1: null },
    tracking_diff_y1: null,
    scale_yi: null,
    mgmt_fee_pct: null,
    custody_fee_pct: null,
    recommend_rank: null,
    ...over
  };
}

describe("百分比 / 涨跌语义", () => {
  it("null 落「—」，不带正负号", () => {
    expect(pctText(null)).toBe(DASH);
  });

  it("正数补 +，负数自带 -，零不补号", () => {
    expect(pctText(1.234)).toBe("+1.23%");
    expect(pctText(-1.234)).toBe("-1.23%");
    expect(pctText(0)).toBe("0.00%");
  });

  it("涨跌类互斥，null / 0 都不上色", () => {
    expect(pctClass(1)).toEqual({
      "etf-cmp__num--rise": true,
      "etf-cmp__num--fall": false
    });
    expect(pctClass(-1)).toEqual({
      "etf-cmp__num--rise": false,
      "etf-cmp__num--fall": true
    });
    expect(pctClass(0)).toEqual({
      "etf-cmp__num--rise": false,
      "etf-cmp__num--fall": false
    });
    expect(pctClass(null)).toEqual({
      "etf-cmp__num--rise": false,
      "etf-cmp__num--fall": false
    });
  });
});

describe("各列格式化：缺失一律「—」", () => {
  it("净值 4 位小数", () => {
    expect(navText(row())).toBe(DASH);
    expect(navText(row({ nav: 3.14159 }))).toBe("3.1416");
  });

  it("成交额分亿 / 万 / 元三档", () => {
    expect(amountText(row())).toBe(DASH);
    expect(amountText(row({ amount: 1.234e8 }))).toBe("1.23亿");
    expect(amountText(row({ amount: 1.234e4 }))).toBe("1.2万");
    expect(amountText(row({ amount: 987 }))).toBe("987");
  });

  it("成交额的档位边界落在「亿」而不是「万」", () => {
    expect(amountText(row({ amount: 1e8 }))).toBe("1.00亿");
    expect(amountText(row({ amount: 1e4 }))).toBe("1.0万");
  });

  it("跟踪差与百分比同形（口径不同，命名分开）", () => {
    expect(trackingText(null)).toBe(DASH);
    expect(trackingText(-0.5)).toBe("-0.50%");
  });

  it("规模两位小数带单位", () => {
    expect(scaleText(row())).toBe(DASH);
    expect(scaleText(row({ scale_yi: 12.345 }))).toBe("12.35亿");
  });

  it("费率：双缺「—」，单缺只显有的那只", () => {
    expect(feeText(row())).toBe(DASH);
    expect(feeText(row({ mgmt_fee_pct: 0.5, custody_fee_pct: 0.1 }))).toBe(
      "管理 0.50% / 托管 0.10%"
    );
    expect(feeText(row({ mgmt_fee_pct: 0.5 }))).toBe("管理 0.50%");
    expect(feeText(row({ custody_fee_pct: 0.1 }))).toBe("托管 0.10%");
  });
});

describe("recommendRowsOf（#2334 优选 Top3）", () => {
  it("只收参评行，按名次升序", () => {
    const picks = recommendRowsOf([
      row({ code: "A", recommend_rank: 2 }),
      row({ code: "B", recommend_rank: 1 }),
      row({ code: "C" })
    ]);
    expect(picks.map(p => p.code)).toEqual(["B", "A"]);
    expect(picks[0].rank).toBe(1);
  });

  it("后端多给也只画 3 只（卡位是 auto-fit 网格，第 4 张会挤成参差两行）", () => {
    const picks = recommendRowsOf([
      row({ code: "1", recommend_rank: 1 }),
      row({ code: "2", recommend_rank: 2 }),
      row({ code: "3", recommend_rank: 3 }),
      row({ code: "4", recommend_rank: 4 })
    ]);
    expect(picks).toHaveLength(3);
  });

  it("全不参评 → 空数组（父层据此整块不渲染，不留空壳标题）", () => {
    expect(recommendRowsOf([row(), row()])).toEqual([]);
  });

  it("跟踪差透传，供小卡与表内同口径显示", () => {
    const [pick] = recommendRowsOf([
      row({ recommend_rank: 1, tracking_diff_y1: -0.42 })
    ]);
    expect(pick.tracking).toBe(-0.42);
  });

  it("名次称谓：第 1 名带「优选」，2/3 名只标名次", () => {
    expect(recommendLabel(1)).toBe("优选 · 第 1");
    expect(recommendLabel(2)).toBe("第 2");
    expect(recommendLabel(3)).toBe("第 3");
  });
});

describe("indexBaselineOf", () => {
  it("任一窗口有值才画基准行", () => {
    expect(
      indexBaselineOf({
        index_code: "000300",
        as_of: null,
        index_returns: { m1: null, m3: 1.2, m6: null, y1: null },
        rows: []
      })
    ).not.toBeNull();
  });

  it("全 null / 缺字段 → null（画一行「—」会被读成「指数收益为 0」）", () => {
    expect(
      indexBaselineOf({
        index_code: "000300",
        as_of: null,
        index_returns: { m1: null, m3: null, m6: null, y1: null },
        rows: []
      })
    ).toBeNull();
    expect(
      indexBaselineOf({ index_code: "000300", as_of: null, rows: [] })
    ).toBeNull();
    expect(indexBaselineOf(null)).toBeNull();
  });

  it("窗口表与列顺序一致（增删窗口必须同步）", () => {
    expect(WINDOWS.map(w => w.key)).toEqual(["m1", "m3", "m6", "y1"]);
    expect(WINDOWS.map(w => w.label)).toEqual([
      "近1月",
      "近3月",
      "近6月",
      "近1年"
    ]);
  });
});

describe("footnoteOf", () => {
  it("有 as_of 时说清 T-1 口径 + 行情来源", () => {
    expect(
      footnoteOf({ index_code: "000300", as_of: "2026-10-24", rows: [] })
    ).toBe("净值截至 2026-10-24（T-1 口径） · 当日行情来自新浪财经");
  });

  it("缺 as_of 时只说来源，不留空分隔符", () => {
    expect(footnoteOf({ index_code: "000300", as_of: null, rows: [] })).toBe(
      "当日行情来自新浪财经"
    );
  });

  it("无数据时空串（父层据此不渲染这一行脚注）", () => {
    expect(footnoteOf(null)).toBe("");
  });
});
