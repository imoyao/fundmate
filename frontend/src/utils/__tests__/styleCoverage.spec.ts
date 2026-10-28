/**
 * 风格覆盖率口径单测（#2628）。
 *
 * 这里钉的是**三种「没有数」不能合并成一件事**：
 * - `null`：没有可覆盖的资产（持仓全是货基/现金）——不是「没同步」；
 * - `0`：有合格品种，但一个都没拿到箱体；
 * - `number`：正常的可覆盖口径覆盖率。
 *
 * 早先直接展示 `coverage_pct`（分母含永远无箱体的货基），实测 121 只持仓只有
 * 2 只有箱体 → 8.35%，用户第一反应是「同步挂了」，而数据其实全在。
 */
import { describe, it, expect } from "vitest";
import {
  NO_ELIGIBLE_COVERAGE_TEXT,
  coverageScopeHint,
  effectiveCoveragePct
} from "@/utils/styleCoverage";

describe("effectiveCoveragePct：优先可覆盖口径", () => {
  it("有 eligible 值时直接用（全量口径被货基稀释也不影响）", () => {
    expect(
      effectiveCoveragePct({ coverage_pct: 8.35, eligible_coverage_pct: 100 })
    ).toBe(100);
  });

  it("eligible 为 null → null（没有可覆盖资产，不折成 0）", () => {
    expect(
      effectiveCoveragePct({ coverage_pct: 0, eligible_coverage_pct: null })
    ).toBeNull();
  });

  it("老响应没有该字段 → 回退全量口径（向后兼容）", () => {
    expect(effectiveCoveragePct({ coverage_pct: 66.67 })).toBe(66.67);
  });

  it("eligible = 0 是合法值（有合格品种但未覆盖），不等于 null", () => {
    expect(
      effectiveCoveragePct({ coverage_pct: 12, eligible_coverage_pct: 0 })
    ).toBe(0);
  });

  it("空数据 → null", () => {
    expect(effectiveCoveragePct(null)).toBeNull();
    expect(effectiveCoveragePct(undefined)).toBeNull();
  });
});

describe("coverageScopeHint：只在两个口径不同时提示", () => {
  it("口径相同时不给噪音", () => {
    expect(
      coverageScopeHint({ coverage_pct: 100, eligible_coverage_pct: 100 })
    ).toBeNull();
  });

  it("口径不同时写明全量值", () => {
    expect(
      coverageScopeHint({ coverage_pct: 8.35, eligible_coverage_pct: 100 })
    ).toBe("含货基/现金的全量口径 8.4%");
  });

  it("没有可覆盖资产时不提示（另有专门文案）", () => {
    expect(
      coverageScopeHint({ coverage_pct: 0, eligible_coverage_pct: null })
    ).toBeNull();
  });
});

describe("NO_ELIGIBLE_COVERAGE_TEXT", () => {
  it("文案必须点明「货基/现金不计入」，否则会被读成没同步", () => {
    expect(NO_ELIGIBLE_COVERAGE_TEXT).toContain("货基");
    expect(NO_ELIGIBLE_COVERAGE_TEXT).toContain("不计入");
  });
});
