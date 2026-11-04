import { describe, expect, it } from "vitest";
import type { FundPerformanceResult } from "@/api/products";
import {
  DASH,
  PEER_METRIC_LABEL,
  daysText,
  drawdownText,
  fmtPct,
  fmtRatio,
  peerText
} from "../perfFormat";
import {
  buildBenchmarkRows,
  buildPeerRows,
  buildRiskRows,
  hasAnyValue
} from "../perfRows";

/** 只给被测函数需要的字段；其余留空，避免测试被无关字段绑住 */
const perf = (over: Partial<FundPerformanceResult> = {}) =>
  ({ fund_kind: "fund", ...over }) as unknown as FundPerformanceResult;

describe("perfFormat：诚实降级", () => {
  it("null / undefined 一律降级「—」，不显示 0", () => {
    expect(fmtPct(null)).toBe(DASH);
    expect(fmtPct(undefined)).toBe(DASH);
    expect(fmtRatio(null)).toBe(DASH);
    expect(drawdownText(null)).toBe(DASH);
    expect(daysText(null)).toBe(DASH);
  });

  it("0 不当作缺失：0% 收益要显 0.00%", () => {
    expect(fmtPct(0)).toBe("0.00%");
    expect(fmtRatio(0)).toBe("0.00");
  });
});

describe("perfFormat：回撤文案", () => {
  it("回撤 0 与 -0.0 都说「正在新高」——在最高点不是一个跌幅", () => {
    expect(drawdownText(0)).toBe("正在新高");
    expect(drawdownText(-0.004)).toBe("正在新高");
    expect(drawdownText(-0)).toBe("正在新高");
  });

  it("真回撤显负数百分比（带符号，避免读成「涨了」）", () => {
    expect(drawdownText(-12.34)).toBe("-12.34%");
    expect(drawdownText(-0.006)).toBe("-0.01%");
  });
});

describe("perfFormat：熬了多久", () => {
  it("档位边界：60 天起按月、365 天起按年", () => {
    expect(daysText(0)).toBe("今天");
    expect(daysText(-3)).toBe("今天");
    expect(daysText(59)).toBe("59 天");
    expect(daysText(60)).toBe("2 个月");
    expect(daysText(364)).toBe("12 个月");
    expect(daysText(365)).toBe("1 年");
    expect(daysText(400)).toBe("1 年 1 个月");
    expect(daysText(800)).toBe("2 年 2 个月");
  });
});

describe("perfFormat：同类分位", () => {
  it("分位折成「前 N%」，且最小是 1%", () => {
    expect(peerText(88)).toBe("前 12%");
    expect(peerText(100)).toBe("前 1%");
    expect(peerText(0)).toBe("前 100%");
  });

  it("键序固定：不随对象键序漂移", () => {
    expect(Object.keys(PEER_METRIC_LABEL)[0]).toBe("current_drawdown");
    expect(Object.keys(PEER_METRIC_LABEL).at(-1)).toBe("win_rate");
  });
});

describe("buildRiskRows", () => {
  it("货币基金没有风险比口径，返回空（不渲染整块）", () => {
    expect(buildRiskRows(perf({ fund_kind: "money" }))).toEqual([]);
    expect(buildRiskRows(null)).toEqual([]);
  });

  it("基金返回 7 条，顺序与设计一致（卡玛→索提诺→夏普→UI→UPI→波回比→拟涨幅）", () => {
    const rows = buildRiskRows(perf());
    expect(rows.map(r => r.key)).toEqual([
      "calmar",
      "sortino",
      "sharpe",
      "ulcer",
      "upi",
      "rrd",
      "shape_gain2"
    ]);
    // 字段全缺时值一律「—」，但仍保留行（行是口径说明，不是数据）
    expect(rows.every(r => r.value === DASH)).toBe(true);
  });

  it("每条都带 hint：不解释口径的比值用户无法复核", () => {
    expect(buildRiskRows(perf()).every(r => !!r.hint)).toBe(true);
  });

  it("拟涨幅读的是嵌套 shape_gain2，不是顶层同名字段", () => {
    const rows = buildRiskRows(
      perf({
        shape_gain2: { shape_gain2: 8.5 }
      } as Partial<FundPerformanceResult>)
    );
    expect(rows.find(r => r.key === "shape_gain2")?.value).toBe("8.50%");
  });

  it("溃疡指数按百分比格式化，其余比值保留 2 位", () => {
    const rows = buildRiskRows(perf({ ulcer_index: 3.456, sharpe: 1.2 }));
    expect(rows.find(r => r.key === "ulcer")?.value).toBe("3.46%");
    expect(rows.find(r => r.key === "sharpe")?.value).toBe("1.20");
  });
});

describe("buildPeerRows", () => {
  it("后端没给分位 → 空数组（样本不足时不画这一块）", () => {
    expect(buildPeerRows(perf())).toEqual([]);
    expect(buildPeerRows(perf({ peer_percentiles: {} }))).toEqual([]);
  });

  it("只取有值的项，且按固定键序而非接口键序", () => {
    // 故意打乱传入顺序：输出必须仍是 current_drawdown → sharpe
    const rows = buildPeerRows(
      perf({ peer_percentiles: { sharpe: 90, current_drawdown: 75 } })
    );
    expect(rows.map(r => r.key)).toEqual(["current_drawdown", "sharpe"]);
  });

  it("值在构造时就折成「前 N%」，模板不再做换算", () => {
    const rows = buildPeerRows(perf({ peer_percentiles: { sharpe: 90 } }));
    expect(rows[0].value).toBe("前 10%");
  });

  it("接口多给的未知指标被忽略（避免渲染无中文标签的行）", () => {
    const rows = buildPeerRows(
      perf({ peer_percentiles: { unknown_metric: 50, sharpe: 66 } as never })
    );
    expect(rows.map(r => r.key)).toEqual(["sharpe"]);
  });
});

describe("buildBenchmarkRows", () => {
  it("基准不可用时返回空（改用 reason 文案，不画一排「—」）", () => {
    expect(buildBenchmarkRows(perf())).toEqual([]);
    expect(
      buildBenchmarkRows(
        perf({ benchmark: { available: false, name: "沪深300" } } as never)
      )
    ).toEqual([]);
  });

  it("可用时给 4 条，超额 / 捕获按百分比，信息比率按比值", () => {
    const rows = buildBenchmarkRows(
      perf({
        benchmark: {
          available: true,
          name: "中证偏股",
          excess_return: 2.5,
          information_ratio: 0.987,
          upside_capture: 105,
          downside_capture: 88
        }
      } as never)
    );
    expect(rows.map(r => r.key)).toEqual(["excess", "ir", "up", "down"]);
    expect(rows.map(r => r.value)).toEqual([
      "2.50%",
      "0.99",
      "105.00%",
      "88.00%"
    ]);
  });
});

describe("hasAnyValue", () => {
  it("全「—」判为无值（这一块就不画）", () => {
    expect(hasAnyValue([{ key: "a", label: "A", value: DASH }])).toBe(false);
    expect(hasAnyValue([])).toBe(false);
  });

  it("有一项有值就算有值", () => {
    expect(
      hasAnyValue([
        { key: "a", label: "A", value: DASH },
        { key: "b", label: "B", value: "1.00" }
      ])
    ).toBe(true);
  });
});
