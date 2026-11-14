import dayjs from "dayjs";
import { describe, expect, it } from "vitest";
import {
  ALL_CHART_RANGE_KEYS,
  CHART_RANGE_LABELS,
  MORE_CHART_RANGE_KEYS,
  PRIMARY_CHART_RANGE_KEYS,
  chartRangeLabel,
  chartRangeParams
} from "../chartRange";

const NOW = dayjs("2026-11-14");

describe("chartRangeParams", () => {
  it("近1月 / 近3月 / 近6月 / 近1年按月回退，终点恒为今日", () => {
    expect(chartRangeParams("1m", NOW)).toEqual({
      start_date: "2026-10-14",
      end_date: "2026-11-14"
    });
    expect(chartRangeParams("3m", NOW).start_date).toBe("2026-08-14");
    expect(chartRangeParams("6m", NOW).start_date).toBe("2026-05-14");
    expect(chartRangeParams("1y", NOW).start_date).toBe("2025-11-14");
  });

  it("近2年 / 近3年 / 近5年按年回退", () => {
    expect(chartRangeParams("2y", NOW).start_date).toBe("2024-11-14");
    expect(chartRangeParams("3y", NOW).start_date).toBe("2023-11-14");
    expect(chartRangeParams("5y", NOW).start_date).toBe("2021-11-14");
  });

  it("今年来 = 当年 1-1 起，不是「近 12 个月」", () => {
    expect(chartRangeParams("ytd", NOW)).toEqual({
      start_date: "2026-01-01",
      end_date: "2026-11-14"
    });
  });

  it("成立来 = inception 哨兵（起点交后端解析）+ 今日终点", () => {
    expect(chartRangeParams("inception", NOW)).toEqual({
      start_date: "inception",
      end_date: "2026-11-14"
    });
  });

  it("月末不溢出：3-31 减 1 月落在 2 月末，不是 3-03", () => {
    // 原生 Date.setMonth 会溢出成 2026-03-03，把「近1月」画成 28 天窗口
    expect(chartRangeParams("1m", dayjs("2026-03-31")).start_date).toBe(
      "2026-02-28"
    );
    // 闰年 2 月末同样夹取
    expect(chartRangeParams("1m", dayjs("2024-03-31")).start_date).toBe(
      "2024-02-29"
    );
  });
});

describe("档位表", () => {
  it("第一排 4 档 + 更多 5 档，合起来 9 档且无重复", () => {
    expect(PRIMARY_CHART_RANGE_KEYS).toEqual(["1m", "3m", "6m", "1y"]);
    expect(MORE_CHART_RANGE_KEYS).toEqual([
      "2y",
      "3y",
      "5y",
      "ytd",
      "inception"
    ]);
    expect(ALL_CHART_RANGE_KEYS).toHaveLength(9);
    expect(new Set(ALL_CHART_RANGE_KEYS).size).toBe(9);
  });

  it("每一档都有中文标签（漏写会让按钮空白）", () => {
    for (const key of ALL_CHART_RANGE_KEYS) {
      expect(CHART_RANGE_LABELS[key]).toBeTruthy();
      expect(chartRangeLabel(key)).toBe(CHART_RANGE_LABELS[key]);
    }
  });
});
