import { describe, expect, it } from "vitest";
import {
  HIGH_THRESHOLD,
  LEGEND,
  MID_THRESHOLD,
  barWidth,
  buildFootnote,
  buildSkippedNote,
  buildSummary,
  tone,
  type AllocData
} from "../allocModel";

const data = (over: Partial<Record<string, unknown>> = {}) =>
  ({
    peers: [],
    window: 250,
    sample_days: 242,
    caveats: [],
    ...over
  }) as unknown as AllocData;

describe("tone：档位边界是闭区间", () => {
  it("ρ ≥ 0.8 就是「风险集中」，不是 > 0.8", () => {
    expect(tone(HIGH_THRESHOLD)).toBe("danger");
    expect(tone(1)).toBe("danger");
    expect(tone(0.799)).toBe("warn");
  });

  it("0.4 起是明显联动", () => {
    expect(tone(MID_THRESHOLD)).toBe("warn");
    expect(tone(0.399)).toBe("low");
  });

  it("−0.4 起是反向对冲，−0.399 仍是弱关联", () => {
    expect(tone(-MID_THRESHOLD)).toBe("hedge");
    expect(tone(-1)).toBe("hedge");
    expect(tone(-0.399)).toBe("low");
  });

  it("0 落弱关联（不强不算对冲）", () => {
    expect(tone(0)).toBe("low");
  });
});

describe("barWidth：半轨百分比", () => {
  it("|ρ| × 50%，四舍五入到整数百分比", () => {
    expect(barWidth(1)).toBe("50%");
    expect(barWidth(-1)).toBe("50%");
    expect(barWidth(0.5)).toBe("25%");
    expect(barWidth(-0.26)).toBe("13%");
    expect(barWidth(0)).toBe("0%");
  });
});

describe("LEGEND", () => {
  it("四档齐全且含阈值，顺序与档位一致", () => {
    expect(LEGEND.map(l => l.tier)).toEqual(["danger", "warn", "hedge", "low"]);
    expect(LEGEND[0].text).toContain(String(HIGH_THRESHOLD));
  });
});

describe("buildSummary：这条才是要让用户看见的话", () => {
  it("没有 peer 就不说话（走空态引导，不说「没有强联动」）", () => {
    expect(buildSummary(0, 0)).toBeNull();
  });

  it("无强联动 → 肯定分散", () => {
    expect(buildSummary(5, 0)).toBe(
      `与你其余 5 只持仓中，没有ρ ≥ ${HIGH_THRESHOLD} 的强联动标的——这一只确实带来了分散。`
    );
  });

  it("有强联动 → 点明「账面分散了，风险未必」", () => {
    expect(buildSummary(5, 2)).toBe(
      `与你其余 5 只持仓中，有 2 只相关系数 ≥ ${HIGH_THRESHOLD}——账面分散了，风险未必。`
    );
  });
});

describe("buildSkippedNote：没进结论的东西要披露", () => {
  it("无跳过项时不显示", () => {
    expect(buildSkippedNote(null)).toBeNull();
    expect(buildSkippedNote(data({ skipped_count: 0 }))).toBeNull();
    expect(buildSkippedNote(data({}))).toBeNull();
  });

  it("有跳过项时带默认重叠天数门槛 60", () => {
    expect(buildSkippedNote(data({ skipped_count: 3 }))).toBe(
      "另有 3 只持仓因同期交易日不足 60 天或无波动未纳入计算"
    );
  });

  it("后端给了门槛就用后端的", () => {
    expect(
      buildSkippedNote(data({ skipped_count: 1, min_overlap: 90 }))
    ).toContain("不足 90 天");
  });
});

describe("buildFootnote：口径 / 窗口 / 样本量", () => {
  it("无数据返回空串（不渲染空脚注）", () => {
    expect(buildFootnote(null)).toBe("");
    expect(buildFootnote(undefined)).toBe("");
  });

  it("没有 basis 时不留下开头的分隔符", () => {
    expect(buildFootnote(data())).toBe("近250窗口 · 基准序列 242 个交易日");
  });

  it("有 basis 与 caveat 时按 · 串起来", () => {
    expect(
      buildFootnote(
        data({ basis: "日收益 Pearson", caveats: ["停牌日已剔除"] })
      )
    ).toBe("日收益 Pearson · 近250窗口 · 基准序列 242 个交易日 · 停牌日已剔除");
  });

  it("多条 caveat 只取第一条（版面只放一行）", () => {
    expect(
      buildFootnote(data({ caveats: ["第一条", "第二条"] })).endsWith("第一条")
    ).toBe(true);
  });
});
