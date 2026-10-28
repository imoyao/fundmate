/**
 * 交易状态口径（#2712）：标签与配色只有一份，共享表格与资产流水页共用。
 */
import { describe, it, expect } from "vitest";
import { txnStatusLabel, txnStatusTag } from "../transactionStatus";

describe("txnStatusLabel", () => {
  it("四种状态有中文", () => {
    expect(txnStatusLabel("success")).toBe("成功");
    expect(txnStatusLabel("failed")).toBe("失败");
    expect(txnStatusLabel("cancelled")).toBe("已撤单");
    expect(txnStatusLabel("pending")).toBe("可撤单");
  });

  it("未知状态原样露出，便于排查数据而不是吞成「未知」", () => {
    expect(txnStatusLabel("weird")).toBe("weird");
  });

  it("空值给占位", () => {
    expect(txnStatusLabel(null)).toBe("--");
    expect(txnStatusLabel(undefined)).toBe("--");
  });
});

describe("txnStatusTag", () => {
  it("成功绿 / 失败红 / 其余中性", () => {
    expect(txnStatusTag("success")).toBe("success");
    expect(txnStatusTag("failed")).toBe("danger");
    expect(txnStatusTag("cancelled")).toBe("info");
    expect(txnStatusTag("pending")).toBe("warning");
  });

  it("未知与空值回落 primary", () => {
    expect(txnStatusTag("weird")).toBe("primary");
    expect(txnStatusTag(null)).toBe("primary");
  });
});
