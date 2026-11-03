import { describe, expect, it } from "vitest";
import { isRedundantSourceOp, visibleSourceOp } from "../sourceOpText";

/**
 * 产品列「券商原文」的展示判据（#2838）。
 *
 * 真实交割单里的原文与操作列的对应关系（同花顺导出）：
 *   证券买入 → 买入、证券卖出 → 卖出、股息红利扣税 → 扣税  ← 这三类是重复
 *   债券兑息 / 利息归本 / 新股入帐 / 配股退款退息 → 操作列说不了 ← 这些要留
 */
describe("券商原文是否只是操作列的另一种写法", () => {
  it("「证券买入」对「买入」：重复", () => {
    expect(isRedundantSourceOp("证券买入", "买入")).toBe(true);
  });

  it("「股息红利扣税」对「扣税」：重复", () => {
    expect(isRedundantSourceOp("股息红利扣税", "扣税")).toBe(true);
  });

  it("「债券兑息」对「现金分红」：不重复——用户靠它判断这句话被认成了什么", () => {
    expect(isRedundantSourceOp("债券兑息", "现金分红")).toBe(false);
  });

  it("「利息归本」对「现金分红」：不重复", () => {
    expect(isRedundantSourceOp("利息归本", "现金分红")).toBe(false);
  });

  it("「送股」对「拆分/送股」：比较时忽略斜杠，判为重复", () => {
    expect(isRedundantSourceOp("送股", "拆分/送股")).toBe(true);
  });

  it("操作标签为空（未映射 / 解析失败）：不判重复，原文是唯一线索", () => {
    expect(isRedundantSourceOp("担保品划转", "")).toBe(false);
  });

  it("单字标签不做包含判断（「买」几乎必中，宁可留着原文）", () => {
    expect(isRedundantSourceOp("证券买入", "买")).toBe(false);
  });

  it("原文为空：不判重复（没有可比的东西）", () => {
    expect(isRedundantSourceOp("", "买入")).toBe(false);
  });
});

describe("visibleSourceOp：产品列该显示什么", () => {
  it("重复的原文返回空串（不渲染）", () => {
    expect(visibleSourceOp({ notes: "证券买入", op_type_label: "买入" })).toBe(
      ""
    );
  });

  it("有信息量的原文原样返回", () => {
    expect(
      visibleSourceOp({ notes: "债券兑息", op_type_label: "现金分红" })
    ).toBe("债券兑息");
  });

  it("脏数据（notes 缺字段 / 只有空白）不抛错也不渲染", () => {
    expect(visibleSourceOp({})).toBe("");
    expect(visibleSourceOp({ notes: "   " })).toBe("");
  });
});
