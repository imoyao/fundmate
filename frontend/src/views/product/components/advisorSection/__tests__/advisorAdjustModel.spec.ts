import { describe, expect, it } from "vitest";
import {
  ADJUST_LIMIT,
  adjustEmptyHint,
  derivedFromSnapshots
} from "../advisorAdjustModel";

describe("derivedFromSnapshots：什么时候必须挂「快照推导」声明", () => {
  it("空列表 → 不声明（还没有记录可声明）", () => {
    expect(derivedFromSnapshots([])).toBe(false);
  });

  it("含 qieman → 声明（`qieman` 是快照推导，仅计划型组合仍走这条）", () => {
    expect(derivedFromSnapshots([{ source: "qieman" }])).toBe(true);
  });

  it("含 qieman_official → 不声明（官方接口数据，不该挂推导免责）", () => {
    expect(derivedFromSnapshots([{ source: "qieman_official" }])).toBe(false);
    expect(
      derivedFromSnapshots([
        { source: "qieman_official" },
        { source: "qieman_official" }
      ])
    ).toBe(false);
  });

  it("同一平台两种来源混排 → 仍要声明（推导行确实存在）", () => {
    expect(
      derivedFromSnapshots([
        { source: "qieman_official" },
        { source: "qieman" }
      ])
    ).toBe(true);
  });

  it("全是 tiantian → 不声明（官方接口，不要给真实数据挂免责）", () => {
    expect(
      derivedFromSnapshots([{ source: "tiantian" }, { source: "tiantian" }])
    ).toBe(false);
  });

  it("混合来源里只要有一组推导就声明（不能只标一部分）", () => {
    expect(
      derivedFromSnapshots([{ source: "tiantian" }, { source: "qieman" }])
    ).toBe(true);
  });

  it("判据跟着 source 走，不跟着平台名——未知来源不误报", () => {
    expect(derivedFromSnapshots([{ source: "howbuy" }])).toBe(false);
  });
});

describe("adjustEmptyHint：空态要说清「为什么没有」", () => {
  it("且慢：解释「官方未收录 → 快照推导 → 需两次快照」", () => {
    expect(adjustEmptyHint("QIEMAN")).toContain("官方接口未收录");
    expect(adjustEmptyHint("QIEMAN")).toContain("持仓快照");
    expect(adjustEmptyHint("QIEMAN")).toContain("2 次快照");
  });

  it("其它平台 / 缺失：保持朴素文案，不编造原因", () => {
    expect(adjustEmptyHint("TIANTIAN")).toBe("暂无调仓记录");
    expect(adjustEmptyHint(null)).toBe("暂无调仓记录");
    expect(adjustEmptyHint(undefined)).toBe("暂无调仓记录");
  });

  it("平台码大小写敏感（后端存的是大写常量，小写不是同一件事）", () => {
    expect(adjustEmptyHint("qieman")).toBe("暂无调仓记录");
  });
});

describe("ADJUST_LIMIT", () => {
  it("与自选速览抽屉同档（3 组）——改它等于改两处的信息密度", () => {
    expect(ADJUST_LIMIT).toBe(3);
  });
});
