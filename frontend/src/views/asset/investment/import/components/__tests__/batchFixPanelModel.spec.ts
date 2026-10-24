/**
 * 批量修正面板的展示口径测试（#980 拆分时补）。
 *
 * 这些字符串直接出现在面板正文里，且**没有截图基线**——写错一个标点、少一个符号，
 * CI 不会红，用户先看到。尤其 `mismatchDiffText` 的正负号：差额为正要显式带「+」，
 * 负号由 `toFixed` 自带，写反了就是「差额 -12.00」与「差额 +-12.00」两种事故。
 */
import { describe, it, expect } from "vitest";
import {
  AUTO_FIELD_LABELS,
  SECTION_LABELS,
  allocationLabelOf,
  autoFixableCountOf,
  filledFieldsLabel,
  mismatchDiffText,
  modeLabelOf,
  repoRevertableOf,
  singleScopeLabelOf
} from "../batchFixPanelModel";

describe("modeLabelOf", () => {
  it("三种形态各有固定文案", () => {
    expect(modeLabelOf("single")).toBe("逐条修正模式");
    expect(modeLabelOf("batch")).toBe("分类批量修正模式");
    expect(modeLabelOf("table")).toBe("请到完整表格处理");
  });

  it("none 与未知形态返回空串（顶部标签靠它 v-if 收起）", () => {
    expect(modeLabelOf("none")).toBe("");
    expect(modeLabelOf("")).toBe("");
  });
});

describe("singleScopeLabelOf", () => {
  it("all 显示「全部问题」", () => {
    expect(singleScopeLabelOf("all")).toBe("全部问题");
  });

  it("其余按分区名显示（含 error，逐条模式下仍可能出现）", () => {
    expect(singleScopeLabelOf("missingCode")).toBe("代码未匹配");
    expect(singleScopeLabelOf("error")).toBe("解析错误");
  });
});

describe("mismatchDiffText", () => {
  it("差额为正时显式带「+」", () => {
    expect(mismatchDiffText({ quantity: 100, price: 1.5, amount: 100 })).toBe(
      "数量×价格 = 150.00，当前金额 100.00，差额 +50.00"
    );
  });

  it("差额为负时只带「-」，不出现「+-」", () => {
    const text = mismatchDiffText({ quantity: 100, price: 1.5, amount: 200 });
    expect(text).toBe("数量×价格 = 150.00，当前金额 200.00，差额 -50.00");
    expect(text).not.toContain("+-");
  });

  it("差额为零时不带符号", () => {
    expect(mismatchDiffText({ quantity: 10, price: 2, amount: 20 })).toContain(
      "差额 0.00"
    );
  });

  it("字段缺失时保留 NaN 文案（既有实现如此，改它属于新的展示决策）", () => {
    expect(mismatchDiffText({ quantity: 1, price: undefined, amount: 1 })).toBe(
      "数量×价格 = NaN，当前金额 1.00，差额 NaN"
    );
  });
});

describe("filledFieldsLabel", () => {
  it("键名翻成人话并用顿号连接", () => {
    expect(filledFieldsLabel({ _autoFilled: ["quantity", "price"] })).toBe(
      "数量、价格"
    );
  });

  it("未知键原样回显（便于发现新增字段漏配文案）", () => {
    expect(filledFieldsLabel({ _autoFilled: ["quantity", "nav"] })).toBe(
      "数量、nav"
    );
  });

  it("没有 _autoFilled 时返回空串", () => {
    expect(filledFieldsLabel({})).toBe("");
  });

  it("文案表只覆盖数量与价格两种（新增字段须同步这里）", () => {
    expect(Object.keys(AUTO_FIELD_LABELS).sort()).toEqual([
      "price",
      "quantity"
    ]);
  });
});

describe("autoFixableCountOf", () => {
  it("无基金记录时只算 mismatch + 已推算", () => {
    expect(autoFixableCountOf(4, 2, false, 10)).toBe(6);
  });

  it("有基金记录时叠加净值抓取条数", () => {
    expect(autoFixableCountOf(4, 2, true, 10)).toBe(16);
  });

  it("全为零时返回 0（顶部按钮据此不渲染）", () => {
    expect(autoFixableCountOf(0, 0, true, 0)).toBe(0);
  });
});

describe("repoRevertableOf", () => {
  it("只收解析期自动置的活钱", () => {
    const rows = [
      { symbol: "204001", allocation: "liquid" },
      { symbol: "204002", allocation: "liquid", _allocationManual: true },
      { symbol: "204003", allocation: "longterm" }
    ];
    expect(repoRevertableOf(rows).map(r => r.symbol)).toEqual(["204001"]);
  });

  it("手动改过的活钱不回退（用户的设置优先）", () => {
    expect(
      repoRevertableOf([{ allocation: "liquid", _allocationManual: true }])
    ).toHaveLength(0);
  });

  it("空列表返回空数组", () => {
    expect(repoRevertableOf([])).toEqual([]);
  });
});

describe("allocationLabelOf", () => {
  it("已知配置目标取中文名", () => {
    expect(allocationLabelOf("liquid")).toBe("活钱");
    expect(allocationLabelOf("longterm")).toBe("长期增值");
  });

  it("未知值原样回显，不吞成空", () => {
    expect(allocationLabelOf("unknown")).toBe("unknown");
  });
});

describe("SECTION_LABELS", () => {
  it("四个分区键齐全，顺序与面板一致", () => {
    expect(Object.keys(SECTION_LABELS)).toEqual([
      "error",
      "missingCode",
      "missingQtyPrice",
      "mismatch"
    ]);
  });
});
