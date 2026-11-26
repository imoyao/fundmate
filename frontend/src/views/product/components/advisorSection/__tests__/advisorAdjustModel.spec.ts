import { describe, expect, it } from "vitest";
import {
  ADJUST_LIMIT,
  adjustEmptyHint,
  derivedFromSnapshots,
  countByTone,
  sourceLabelOf
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
  it("详情页取 10 组——抽屉 3 组是提示位，两者刻意不同档", () => {
    expect(ADJUST_LIMIT).toBe(10);
  });
});

describe("countByTone：加 / 减计数要把两套用词都收进来", () => {
  const group = (ops: (string | null)[]) => ({
    adjust_date: "2026-10-28",
    reason: null,
    source: "qieman",
    items: ops.map((op_name, i) => ({
      fund_code: `00000${i}`,
      fund_name: null,
      op_name,
      pre_ratio: 10,
      after_ratio: 12
    }))
  });

  it("天天 / 快照那套用词（加仓、减仓）", () => {
    expect(countByTone(group(["加仓", "减仓", "加仓"]))).toEqual({
      add: 2,
      cut: 1
    });
  });

  it("且慢官方那套用词（调入、调增 / 调出、调减）同样计入", () => {
    // 漏掉官方用词的后果不是报错，而是整片计数变 0 —— 用户会以为调仓记录坏了
    expect(countByTone(group(["调入", "调增", "调出", "调减"]))).toEqual({
      add: 2,
      cut: 2
    });
  });

  it("持平 / 未知动作 / 缺失不计入两侧（它们不是方向）", () => {
    expect(countByTone(group(["持平", null, "申购"]))).toEqual({
      add: 0,
      cut: 0
    });
  });
});

describe("sourceLabelOf：来源标注要一眼看出「不是官方披露」", () => {
  it("四个已知来源各有中文标注", () => {
    expect(sourceLabelOf("qieman_official")).toBe("官方披露");
    expect(sourceLabelOf("qieman")).toBe("快照推导");
    expect(sourceLabelOf("tiantian")).toBe("天天官方");
    expect(sourceLabelOf("qieman_manual")).toBe("手动导入");
  });

  it("未知来源原样透出，不伪装成已知来源", () => {
    expect(sourceLabelOf("howbuy")).toBe("howbuy");
  });
});
