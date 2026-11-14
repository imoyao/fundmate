import { describe, expect, it } from "vitest";
import type { BenchmarkExcessResult } from "@/api/summary";
import { excessCaptionOf, excessDegradHint } from "../benchmarkExcess";

/**
 * 降级原因 → 文案的**唯一出口**（超额卡、基准卡、超额走势空态三处共用）。
 *
 * 钉住两件事：①后端每个 `range_reason` 都有话可说，不允许落回「暂无可比数据」
 * 这种把四种成因混成一句的兜底（用户会当成功能坏了）；②可算时不给任何提示。
 */
function make(reason: string | null): BenchmarkExcessResult {
  return {
    scope: "portfolio",
    ledger_id: null,
    portfolio_id: 1,
    start_date: "2026-10-14",
    end_date: "2026-11-14",
    range_rate: null,
    range_pnl: null,
    range_baseline: null,
    range_reason: reason,
    benchmark: {
      code: "000300.SH",
      name: "沪深300",
      range_return: null,
      bench_start_date: null,
      bench_end_date: null,
      reason: null
    },
    excess_return: null,
    series: []
  } as BenchmarkExcessResult;
}

describe("excessDegradHint（区间收益侧的降级说明）", () => {
  it("组合级新增的两档各有独立文案，不落回兜底", () => {
    expect(excessDegradHint(make("no_baseline"))).toContain("尚无资产");
    expect(excessDegradHint(make("baseline_missing"))).toContain("基线不完整");
    expect(excessDegradHint(make("no_computable_day"))).toContain("盈亏");
  });

  it("起点资产失真（D104）说清是「无可比性」而不是「没数据」", () => {
    expect(excessDegradHint(make("baseline_not_representative"))).toContain(
      "资产过小"
    );
  });

  it("可算时返回空串（卡片据此决定要不要挂说明）", () => {
    expect(excessDegradHint(make(null))).toBe("");
    expect(excessDegradHint(null)).toBe("");
  });

  it("收益侧原因优先于指数侧（同一张卡只说最根本的一条）", () => {
    const data = make("no_baseline");
    data.benchmark.reason = "non_cn_a_holdings";

    expect(excessDegradHint(data)).toContain("尚无资产");
  });
});

describe("excessCaptionOf（三条数值齐全才给对比式）", () => {
  it("齐全时是「区间 · 组合 vs 基准」", () => {
    const data = make(null);
    data.range_rate = 3.2;
    data.benchmark.range_return = 1.1;
    data.excess_return = 2.1;

    expect(excessCaptionOf(data, "近1月")).toBe("近1月 · +3.20% vs +1.10%");
  });

  it("缺一项就退回降级说明，不拼半截对比", () => {
    const data = make("baseline_missing");
    data.range_rate = null;
    data.benchmark.range_return = 1.1;

    expect(excessCaptionOf(data, "近1月")).toContain("基线不完整");
  });
});
