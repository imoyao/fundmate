/**
 * 三步准入「展示态」的单测：钉住两件事——
 *   ① 步骤编号只由 guard 的阻塞原因推导，不另造一套准入判据；
 *   ② 打开弹窗时给的是「下一步」引导，不是命令式报错。
 */
import { describe, expect, it } from "vitest";
import { ENRICH_STEPS, describeEnrichSteps } from "../enrichSteps";
import type { EnrichGuardInput } from "../danglingRefRemediationGuard";

const READY: EnrichGuardInput = {
  preview: { symbol: "600519", trade_date: "2026-11-07" },
  hasField: true,
  needsFill: true,
  fieldSignature: "600519|2026-11-07",
  confirmed: true,
  previewing: false,
  submitting: false,
  txnCount: 3
};

describe("补全弹窗三步准入的展示态", () => {
  it("清单固定三条，顺序不随后端枚举漂移", () => {
    expect(ENRICH_STEPS.map(s => s.title)).toEqual([
      "填缺失信息",
      "查看影响",
      "核对并确认"
    ]);
  });

  it("刚打开：停在第 1 步，引导语说下一步而不是报错", () => {
    const state = describeEnrichSteps({
      ...READY,
      hasField: false,
      preview: null,
      confirmed: false
    });
    expect(state.current).toBe(1);
    expect(state.completed).toBe(0);
    expect(state.blocked).toBe(true);
    expect(state.guide).toContain("下一步");
    expect(state.guide).not.toContain("请至少");
  });

  it("填完但没看预览：停在第 2 步", () => {
    const state = describeEnrichSteps({
      ...READY,
      preview: null,
      confirmed: false
    });
    expect(state.current).toBe(2);
    expect(state.guide).toContain("查看影响");
  });

  it("预览后输入变了：仍停在第 2 步，提示重新查看", () => {
    const state = describeEnrichSteps({
      ...READY,
      fieldSignature: "000001|2026-11-07"
    });
    expect(state.current).toBe(2);
    expect(state.guide).toContain("重新查看");
  });

  it("预览齐、未勾选：停在第 3 步", () => {
    const state = describeEnrichSteps({ ...READY, confirmed: false });
    expect(state.current).toBe(3);
    expect(state.guide).toContain("勾选");
  });

  it("三步就绪：无阻塞", () => {
    const state = describeEnrichSteps(READY);
    expect(state.current).toBeNull();
    expect(state.completed).toBe(3);
    expect(state.blocked).toBe(false);
  });

  it("判据仍由 guard 持有：预览中 / 提交中都算阻塞", () => {
    for (const input of [
      { ...READY, previewing: true },
      { ...READY, submitting: true }
    ]) {
      expect(describeEnrichSteps(input).blocked).toBe(true);
    }
  });

  it("空组：如实说明没有可处理交易", () => {
    const state = describeEnrichSteps({ ...READY, txnCount: 0 });
    expect(state.current).toBe(1);
    expect(state.guide).toContain("没有可处理的交易");
  });

  it("无可补字段：停在第 1 步，且引导语说清「都已填写」并给出下一步", () => {
    const state = describeEnrichSteps({
      ...READY,
      needsFill: false,
      hasField: false,
      preview: null,
      confirmed: false
    });
    expect(state.current).toBe(1);
    expect(state.blocked).toBe(true);
    expect(state.guide).toContain("都已填写");
    expect(state.guide).toContain("没有可补的字段");
    expect(state.guide).not.toContain("请至少");
  });
});
