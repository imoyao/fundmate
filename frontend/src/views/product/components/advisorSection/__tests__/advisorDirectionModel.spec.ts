import { describe, expect, it } from "vitest";
import type { AdvisorStyleDirection } from "@/api/funds";
import {
  BIG_DIFF_PP,
  barScaleOf,
  barWidthPct,
  buildDirectionRows,
  diffText,
  divergenceText,
  mostDivergent
} from "../advisorDirectionModel";

const d = (key: string, value: number): AdvisorStyleDirection => ({
  key,
  value
});

describe("buildDirectionRows：两侧配成行", () => {
  it("没有组合侧骨架 → 空数组（不能只画我这一侧）", () => {
    expect(buildDirectionRows([], [d("大盘", 20)])).toEqual([]);
    expect(buildDirectionRows(undefined, undefined)).toEqual([]);
  });

  it("以组合侧为骨架，我侧缺失的方向补 0（不是丢行）", () => {
    const rows = buildDirectionRows(
      [d("大盘", 18.82), d("固收", 7.28)],
      [d("大盘", 19.74)]
    );
    expect(rows.map(r => r.key)).toEqual(["大盘", "固收"]);
    expect(rows[1]).toMatchObject({
      adv: 7.28,
      mine: 0,
      diff: -7.3,
      big: true
    });
  });

  it("差值 = 我 − 组合，保留 1 位", () => {
    const [row] = buildDirectionRows([d("中盘", 34.58)], [d("中盘", 18.34)]);
    expect(row.diff).toBe(-16.2);
  });

  it("阈值边界：4.9pp 不点，5.0pp 点（颜色是唯一另色提示，边界必须钉死）", () => {
    const [small] = buildDirectionRows([d("大盘", 10)], [d("大盘", 14.9)]);
    const [exact] = buildDirectionRows([d("大盘", 10)], [d("大盘", 15)]);
    expect(BIG_DIFF_PP).toBe(5);
    expect(small.big).toBe(false);
    expect(exact.big).toBe(true);
  });

  it("负数方向差也按绝对值判（我低 5pp 同样是「方向不一致」）", () => {
    const [row] = buildDirectionRows([d("固收", 30)], [d("固收", 25)]);
    expect(row.diff).toBe(-5);
    expect(row.big).toBe(true);
  });
});

describe("mostDivergent：只点最不一致的 N 档", () => {
  const rows = buildDirectionRows(
    [
      d("大盘", 18.82),
      d("中盘", 34.58),
      d("小盘", 31.96),
      d("港股", 7.36),
      d("固收", 7.28)
    ],
    [
      d("大盘", 19.74),
      d("中盘", 18.34),
      d("小盘", 30.71),
      d("港股", 5.03),
      d("固收", 26.17)
    ]
  );

  it("默认两档，按绝对差降序", () => {
    expect(mostDivergent(rows).map(r => r.key)).toEqual(["固收", "中盘"]);
  });

  it("不超过行数", () => {
    expect(mostDivergent(rows, 99)).toHaveLength(5);
    expect(mostDivergent([], 2)).toEqual([]);
  });

  it("不改动入参顺序（调用方还要按原序渲染）", () => {
    const before = rows.map(r => r.key);
    mostDivergent(rows);
    expect(rows.map(r => r.key)).toEqual(before);
  });
});

describe("文案", () => {
  it("divergenceText：高的一侧在前，读起来先看到结构差异", () => {
    const [mineHigher] = buildDirectionRows(
      [d("固收", 7.28)],
      [d("固收", 26.17)]
    );
    const [advHigher] = buildDirectionRows(
      [d("中盘", 34.58)],
      [d("中盘", 18.34)]
    );
    expect(divergenceText(mineHigher)).toBe("我 26.17% · 组合 7.28%");
    expect(divergenceText(advHigher)).toBe("组合 34.58% · 我 18.34%");
  });

  it("divergenceText：两侧相等时按「组合 · 我」原序", () => {
    const [row] = buildDirectionRows([d("大盘", 18.5)], [d("大盘", 18.5)]);
    expect(divergenceText(row)).toBe("组合 18.50% · 我 18.50%");
  });

  it("diffText：正数带 +，0 不带符号（+0.0 读起来像涨）", () => {
    expect(diffText(2.34)).toBe("+2.3");
    expect(diffText(-16.2)).toBe("-16.2");
    expect(diffText(0)).toBe("0.0");
    expect(diffText(-0.04)).toBe("0.0");
  });
});

describe("条形刻度：按两侧实测最大值归一（不是 100%）", () => {
  const rows = buildDirectionRows(
    [d("大盘", 18.82), d("中盘", 34.58)],
    [d("大盘", 19.74), d("中盘", 18.34)]
  );

  it("分母取 adv / mine 的全局最大值", () => {
    // 34.58 是中盘的组合值，也是两侧最大；我侧的 19.74 比它小
    expect(barScaleOf(rows)).toBe(34.58);
  });

  it("最大的一档拉满 100%，其余按比例", () => {
    expect(barWidthPct(34.58, 34.58)).toBe("100.0%");
    expect(barWidthPct(18.82, 34.58)).toBe("54.4%");
  });

  it("最小宽度 1%：极小但不为 0 的占比也要看得见", () => {
    expect(barWidthPct(0, 34.58)).toBe("1.0%");
  });

  it("空数据不除零（兜底 1，避免 NaN 宽度把条画成满格）", () => {
    expect(barScaleOf([])).toBe(1);
    expect(barWidthPct(0, barScaleOf([]))).toBe("1.0%");
  });
});
