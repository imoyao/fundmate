/**
 * 重叠矩阵铺格（#2686）。
 *
 * 钉住的是**六种格子不能互相顶替**：
 * - 自比（对角线）不是 100%；
 * - 零重叠是 0%，不是「没有这一格」；
 * - 披露口径不同是「不可比」，**不是 0%**（显示 0% 会给出「不重叠」的错误安心）；
 * - 档位颜色只按后端 `overlap_level` 映射，前端不二次推导阈值。
 */
import { describe, it, expect } from "vitest";
import type {
  HoldingOverlapData,
  OverlapFund,
  OverlapPair
} from "@/api/holdingOverlap";
import {
  MATRIX_MAX_FUNDS,
  buildOverlapMatrix,
  canRenderMatrix
} from "../holdingOverlapMatrix";

const fund = (over: Partial<OverlapFund> = {}): OverlapFund => ({
  fund_code: "110011",
  symbol: "110011",
  name: "易方达优质精选",
  market_value_cents: 1_000_000,
  report_period: "2026Q2",
  basis: "full",
  ...over
});

const pair = (over: Partial<OverlapPair> = {}): OverlapPair => ({
  fund_code_a: "110011",
  fund_name_a: "易方达优质精选",
  report_period_a: "2026Q2",
  fund_code_b: "005827",
  fund_name_b: "易方达蓝筹精选",
  report_period_b: "2026Q2",
  holding_basis: "full",
  jaccard: 0.6,
  weighted_overlap: 18.5,
  overlap_amount_cents: 120000,
  overlap_level: "duplicate",
  overlap_reason: "共同重仓 6 只、18.5% 仓位重叠",
  common_holdings: [],
  ...over
});

const data = (over: Partial<HoldingOverlapData> = {}): HoldingOverlapData => ({
  pairs: [],
  funds: [],
  fund_count: 0,
  skipped_basis_mismatch: 0,
  skipped_null_ratio: 0,
  total_market_value_cents: 0,
  coverage_pct: 100,
  uncovered: [],
  duplicate_count: 0,
  weak_count: 0,
  min_overlap_amount_cents: 100000,
  caveats: [],
  degraded: false,
  source: "fund_holdings",
  ...over
});

const threeFunds = [
  fund(),
  fund({ fund_code: "005827", symbol: "005827", name: "易方达蓝筹精选" }),
  fund({ fund_code: "161725", symbol: "161725", name: "招商中证白酒" })
];

describe("buildOverlapMatrix：铺满行列", () => {
  it("三只基金只有一对重叠，矩阵仍然是 3×3", () => {
    const matrix = buildOverlapMatrix(
      data({ funds: threeFunds, pairs: [pair()], fund_count: 3 })
    );

    expect(matrix.funds).toHaveLength(3);
    expect(matrix.rows).toHaveLength(3);
    expect(matrix.rows.every(row => row.cells.length === 3)).toBe(true);
  });

  it("对角线是自比，不写成 100%", () => {
    const matrix = buildOverlapMatrix(data({ funds: threeFunds }));
    const cell = matrix.rows[0].cells[0];

    expect(cell.tone).toBe("self");
    expect(cell.text).toBe("—");
  });

  it("有重叠的对显示百分比并按档位上色，且上下三角对称", () => {
    const matrix = buildOverlapMatrix(
      data({ funds: threeFunds, pairs: [pair()] })
    );

    expect(matrix.rows[0].cells[1].text).toBe("18.5%");
    expect(matrix.rows[0].cells[1].tone).toBe("high");
    // 对称：矩阵是两两比较，a-b 与 b-a 必须是同一格
    expect(matrix.rows[1].cells[0].text).toBe("18.5%");
    expect(matrix.rows[1].cells[0].tone).toBe("high");
  });

  it("零重叠是 0%，不是空单元格", () => {
    const matrix = buildOverlapMatrix(
      data({ funds: threeFunds, pairs: [pair()] })
    );

    expect(matrix.rows[0].cells[2].text).toBe("0%");
    expect(matrix.rows[0].cells[2].tone).toBe("none");
  });

  it("披露口径不同 → 不可比，且说明原因（绝不画成 0%）", () => {
    const matrix = buildOverlapMatrix(
      data({
        funds: [fund(), fund({ fund_code: "005827", basis: "top10" })]
      })
    );

    const cell = matrix.rows[0].cells[1];
    expect(cell.tone).toBe("incomparable");
    expect(cell.text).toBe("不可比");
    expect(cell.title).toContain("口径不同");
    // 即使后端恰好给了这对（不该给），口径不同仍优先于数值
    const withPair = buildOverlapMatrix(
      data({
        funds: [fund(), fund({ fund_code: "005827", basis: "top10" })],
        pairs: [pair()]
      })
    );
    expect(withPair.rows[0].cells[1].tone).toBe("incomparable");
  });
});

describe("档位映射：只认后端 overlap_level", () => {
  it.each([
    ["duplicate", "high"],
    ["watch", "mid"],
    ["low", "low"],
    ["trivial", "low"],
    ["same-series", "low"]
  ] as const)("%s → %s", (level, tone) => {
    const matrix = buildOverlapMatrix(
      data({
        funds: threeFunds,
        pairs: [
          pair({ overlap_level: level, overlap_reason: "", jaccard: 0.1 })
        ]
      })
    );

    expect(matrix.rows[0].cells[1].tone).toBe(tone);
  });
});

describe("上限与降级", () => {
  it("超过上限时截断并如实告知被折叠的只数", () => {
    const many = Array.from({ length: MATRIX_MAX_FUNDS + 3 }, (_, i) =>
      fund({ fund_code: String(i).padStart(6, "0"), name: `基金${i}` })
    );

    const matrix = buildOverlapMatrix(data({ funds: many }));

    expect(matrix.funds).toHaveLength(MATRIX_MAX_FUNDS);
    expect(matrix.truncated).toBe(3);
  });

  it("没有资金/数据时返回空矩阵，不抛异常", () => {
    expect(buildOverlapMatrix(null).rows).toHaveLength(0);
    expect(canRenderMatrix(buildOverlapMatrix(data()))).toBe(false);
  });

  it("只有 1 只基金时不给矩阵（没有「两两」可言）", () => {
    const matrix = buildOverlapMatrix(data({ funds: [fund()] }));

    expect(canRenderMatrix(matrix)).toBe(false);
    expect(matrix.rows[0].cells).toHaveLength(1);
  });
});
