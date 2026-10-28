/**
 * 相关性矩阵铺格（#2686 第二交付）。
 *
 * 钉住的是**「没有值」不能被读成「不相关」**：
 * - 无净值 / 样本不足 / 无波动三种原因文案必须不同（否则用户以为是一回事）；
 * - 它们与「取数缺口」也要分开（后者是 bug，前者是数据现状）；
 * - 算不出的对不得进「低相关」档（那会让「没数据」看起来像「分散有效」）。
 */
import { describe, it, expect } from "vitest";
import type {
  CorrelationCell,
  CorrelationFund,
  HoldingCorrelationData
} from "@/api/holdingOverlap";
import {
  buildCorrelationMatrix,
  canRenderCorrelation,
  computedRatioText,
  correlationTone,
  formatRho,
  tallyCorrelation
} from "../holdingCorrelationMatrix";

const fund = (over: Partial<CorrelationFund> = {}): CorrelationFund => ({
  fund_code: "110011",
  symbol: "110011",
  name: "易方达优质精选",
  market_value_cents: 1_000_000,
  market_value_pct: 10,
  ...over
});

const cell = (over: Partial<CorrelationCell> = {}): CorrelationCell => ({
  fund_code_a: "110011",
  fund_code_b: "005827",
  correlation: 0.62,
  overlap_days: 240,
  status: "ok",
  reason: "",
  ...over
});

const data = (
  over: Partial<HoldingCorrelationData> = {}
): HoldingCorrelationData => ({
  window: "1Y",
  min_overlap: 60,
  funds: [],
  cells: [],
  fund_count: 0,
  computed_pairs: 0,
  total_pairs: 0,
  truncated: { count: 0, market_value_pct: 0 },
  matrix_rule: { coverage_target: 0.9, max_members: 20, min_members: 8 },
  caveats: [],
  degraded: false,
  source: "daily_worth/price_history",
  ...over
});

const threeFunds = [
  fund(),
  fund({ fund_code: "005827", symbol: "005827", name: "易方达蓝筹精选" }),
  fund({ fund_code: "161725", symbol: "161725", name: "招商中证白酒" })
];

describe("buildCorrelationMatrix：铺满行列且对称", () => {
  it("三只基金即使只有一对结果也是 3×3，对角线是自比", () => {
    const matrix = buildCorrelationMatrix(
      data({ funds: threeFunds, cells: [cell()], fund_count: 3 })
    );

    expect(matrix.rows).toHaveLength(3);
    expect(matrix.rows.every(row => row.cells.length === 3)).toBe(true);
    expect(matrix.rows[0].cells[0].tone).toBe("self");
    expect(matrix.rows[0].cells[0].text).toBe("—");
    // 矩阵是两两比较：a-b 与 b-a 必须同格
    expect(matrix.rows[0].cells[1].text).toBe("0.62");
    expect(matrix.rows[1].cells[0].text).toBe("0.62");
  });

  it("缺失的一对显示取数缺口，而不是算不出也不装成 0", () => {
    const matrix = buildCorrelationMatrix(
      data({ funds: threeFunds, cells: [{ ...cell() }] })
    );

    const missing = matrix.rows[0].cells[2];
    expect(missing.tone).toBe("unavailable");
    expect(missing.text).toBe("—");
    expect(missing.title).toContain("取数缺口");
  });
});

describe("ρ 分档与文案", () => {
  it.each([
    [0.9, "high"],
    [0.8, "high"],
    [0.6, "mid"],
    [0.1, "low"],
    [-0.3, "low"],
    [-0.5, "negative"]
  ] as const)("%s → %s", (rho, tone) => {
    expect(correlationTone(rho)).toBe(tone);
  });

  it("两位小数，负号保留", () => {
    expect(formatRho(0.6234)).toBe("0.62");
    expect(formatRho(-0.5)).toBe("-0.50");
    expect(formatRho(null)).toBe("—");
  });
});

describe("三种算不出：文案必须不同", () => {
  it.each([
    ["no_series", "无净值"],
    ["short_overlap", "样本不足"],
    ["zero_variance", "无波动"]
  ] as const)("%s → %s", (status, text) => {
    const matrix = buildCorrelationMatrix(
      data({
        funds: [fund(), fund({ fund_code: "005827", symbol: "005827" })],
        cells: [
          cell({
            status,
            correlation: null,
            reason: "同期交易日不足（12 < 60）",
            overlap_days: 12
          })
        ]
      })
    );

    const view = matrix.rows[0].cells[1];
    expect(view.text).toBe(text);
    expect(view.tone).toBe("unavailable");
    // 原因与样本数进 title：用户能自己判断「差多少」
    expect(view.title).toContain("12");
  });

  it("算不出的对不会被计入「低相关」档", () => {
    const tally = tallyCorrelation([
      cell({ correlation: 0.1 }),
      cell({ correlation: 0.9 }),
      cell({ status: "short_overlap", correlation: null })
    ]);

    expect(tally.ok).toBe(2);
    expect(tally.high).toBe(1);
    expect(tally.unavailable).toBe(1);
  });
});

describe("截断与可算出比例", () => {
  it("未覆盖时文案给出只数与市值占比", () => {
    const matrix = buildCorrelationMatrix(
      data({
        funds: threeFunds,
        fund_count: 96,
        truncated: { count: 76, market_value_pct: 33.4 }
      })
    );

    expect(matrix.truncatedCount).toBe(76);
    expect(matrix.coveragePct).toBeCloseTo(66.6, 1);
    expect(matrix.coverageText).toContain("未展开");
    expect(matrix.coverageText).toContain("33.4%");
    expect(matrix.coverageText).toContain("仅代表已展开部分");
  });

  it("全量展开时文案说明覆盖全部", () => {
    const matrix = buildCorrelationMatrix(
      data({ funds: threeFunds, fund_count: 3 })
    );

    expect(matrix.coverageText).toContain("全部 3 只");
  });

  it("不足 2 只时说明算不出而不是「不相关」", () => {
    const matrix = buildCorrelationMatrix(
      data({ funds: [fund()], fund_count: 1 })
    );

    expect(matrix.coverageText).toContain("不足 2 只");
    expect(canRenderCorrelation(matrix)).toBe(false);
  });

  it("可算出比例：0/0 显示 —，否则给分母", () => {
    const empty = buildCorrelationMatrix(data());
    expect(computedRatioText(empty)).toBe("—");

    const partial = buildCorrelationMatrix(
      data({ funds: threeFunds, computed_pairs: 3, total_pairs: 4 })
    );
    expect(computedRatioText(partial)).toBe("3/4（75.0%）");
  });

  it("入参缺失时返回空矩阵，不抛异常", () => {
    expect(buildCorrelationMatrix(null).rows).toHaveLength(0);
    expect(canRenderCorrelation(buildCorrelationMatrix(null))).toBe(false);
  });
});
