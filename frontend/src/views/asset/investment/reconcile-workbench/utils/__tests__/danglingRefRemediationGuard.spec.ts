/**
 * 「数据缺失」补全 / 删除弹窗提交准入的单测（#2866 后续）。
 *
 * 钉住三件会让「显式、安全地处理 blocked 数据」失效的事：
 *   ① 预览未返回 / 预览中 / 提交中 / 输入已变 / 未勾选确认就允许提交；
 *   ② 删除没有输入「删除」二字就允许提交；
 *   ③ 判据顺序被改坏（多个条件同时命中时应返回优先级最高的那条原因）。
 * 断言落在**具体原因文案**上，而不只是「按钮 disabled 属性存在」——Vue 子组件
 * render 抛错时 DOM 会冻结在末次成功渲染，只数锚点会假绿。
 */
import { describe, expect, it } from "vitest";
import {
  buildFieldSignature,
  canSubmitDelete,
  canSubmitEnrich,
  deleteBlockReason,
  enrichBlockReason,
  type DeleteGuardInput,
  type EnrichGuardInput
} from "../danglingRefRemediationGuard";

/** 一份「已看过预览、字段齐、签名一致、已勾选」的基准输入 */
const ENRICH_READY: EnrichGuardInput = {
  preview: { symbol: "600519", trade_date: "2026-11-07" },
  hasField: true,
  needsFill: true,
  fieldSignature: "600519|2026-11-07",
  confirmed: true,
  previewing: false,
  submitting: false,
  txnCount: 3
};

/** 一份「已看过预览、确认词正确」的基准输入 */
const DELETE_READY: DeleteGuardInput = {
  preview: { txn_count: 3 },
  confirmPhrase: "删除",
  previewing: false,
  submitting: false,
  txnCount: 3
};

describe("buildFieldSignature", () => {
  it("按 symbol|tradeDate 拼签名，null/undefined 一律折算成空串", () => {
    expect(buildFieldSignature("600519", "2026-11-07")).toBe(
      "600519|2026-11-07"
    );
    expect(buildFieldSignature(null, null)).toBe("|");
    expect(buildFieldSignature(undefined, "2026-11-07")).toBe("|2026-11-07");
  });
});

describe("补全信息的提交准入（#2866 后续）", () => {
  it("空组：一条可处理交易都没有就钉死", () => {
    const input = { ...ENRICH_READY, txnCount: 0 };
    expect(enrichBlockReason(input)).toBe("该组没有可处理的交易");
    expect(canSubmitEnrich(input)).toBe(false);
  });

  it("没填标的代码也没填交易日期", () => {
    const input = { ...ENRICH_READY, hasField: false };
    expect(enrichBlockReason(input)).toBe("请至少填写标的代码或交易日期");
    expect(canSubmitEnrich(input)).toBe(false);
  });

  it("这组没有可补的字段：不许提交，且原因不是「你没填」", () => {
    const input = { ...ENRICH_READY, needsFill: false, hasField: false };
    expect(enrichBlockReason(input)).toBe("这组没有可补的字段");
    expect(canSubmitEnrich(input)).toBe(false);
  });

  it("判据顺序：无可补字段优先于「请至少填写」（否则会把语义问题说成漏填）", () => {
    const input = { ...ENRICH_READY, needsFill: false, hasField: false };
    expect(enrichBlockReason(input)).not.toBe("请至少填写标的代码或交易日期");
  });

  it("判据顺序：空组优先于无可补字段", () => {
    const input = { ...ENRICH_READY, txnCount: 0, needsFill: false };
    expect(enrichBlockReason(input)).toBe("该组没有可处理的交易");
  });

  it("预览请求进行中不允许提交", () => {
    const input = { ...ENRICH_READY, previewing: true };
    expect(enrichBlockReason(input)).toBe("正在查看影响");
    expect(canSubmitEnrich(input)).toBe(false);
  });

  it("提交进行中不允许重复提交", () => {
    const input = { ...ENRICH_READY, submitting: true };
    expect(enrichBlockReason(input)).toBe("正在提交");
    expect(canSubmitEnrich(input)).toBe(false);
  });

  it("预览未返回前不允许提交", () => {
    const input = { ...ENRICH_READY, preview: null };
    expect(enrichBlockReason(input)).toBe("请先查看影响");
    expect(canSubmitEnrich(input)).toBe(false);
  });

  it("输入已变化：签名对不上旧预览就作废", () => {
    const input = { ...ENRICH_READY, fieldSignature: "000001|2026-11-07" };
    expect(enrichBlockReason(input)).toBe("输入已变化，请重新查看影响");
    expect(canSubmitEnrich(input)).toBe(false);
  });

  it("预览本身的 symbol/trade_date 与当前签名不一致也算输入变化", () => {
    const input = {
      ...ENRICH_READY,
      preview: { symbol: "000001", trade_date: "2026-11-07" }
    };
    expect(enrichBlockReason(input)).toBe("输入已变化，请重新查看影响");
    expect(canSubmitEnrich(input)).toBe(false);
  });

  it("未勾选二次确认不允许提交", () => {
    const input = { ...ENRICH_READY, confirmed: false };
    expect(enrichBlockReason(input)).toBe("请先勾选二次确认");
    expect(canSubmitEnrich(input)).toBe(false);
  });

  it("反向对照：字段齐、预览齐、签名一致、已勾选才允许提交", () => {
    expect(enrichBlockReason(ENRICH_READY)).toBeNull();
    expect(canSubmitEnrich(ENRICH_READY)).toBe(true);
  });

  it("判据顺序：空组优先于其它未就绪条件", () => {
    const input = {
      ...ENRICH_READY,
      txnCount: 0,
      hasField: false,
      preview: null,
      confirmed: false
    };
    expect(enrichBlockReason(input)).toBe("该组没有可处理的交易");
  });

  it("判据顺序：预览中优先于「预览未返回」", () => {
    const input = { ...ENRICH_READY, preview: null, previewing: true };
    expect(enrichBlockReason(input)).toBe("正在查看影响");
  });
});

describe("删除的提交准入（#2866 后续）", () => {
  it("空组：一条可处理交易都没有就钉死", () => {
    const input = { ...DELETE_READY, txnCount: 0 };
    expect(deleteBlockReason(input)).toBe("该组没有可处理的交易");
    expect(canSubmitDelete(input)).toBe(false);
  });

  it("预览请求进行中不允许提交", () => {
    const input = { ...DELETE_READY, previewing: true };
    expect(deleteBlockReason(input)).toBe("正在查看影响");
    expect(canSubmitDelete(input)).toBe(false);
  });

  it("提交进行中不允许重复提交", () => {
    const input = { ...DELETE_READY, submitting: true };
    expect(deleteBlockReason(input)).toBe("正在提交");
    expect(canSubmitDelete(input)).toBe(false);
  });

  it("预览未返回前不允许提交", () => {
    const input = { ...DELETE_READY, preview: null };
    expect(deleteBlockReason(input)).toBe("请先查看影响");
    expect(canSubmitDelete(input)).toBe(false);
  });

  it("确认词错误：空串 / 少一字 / 带空格都不算「删除」二字", () => {
    for (const phrase of ["", "删", "删除 ", " 删除", "delete"]) {
      const input = { ...DELETE_READY, confirmPhrase: phrase };
      expect(deleteBlockReason(input)).toBe("请输入「删除」二字确认");
      expect(canSubmitDelete(input)).toBe(false);
    }
  });

  it("反向对照：预览齐、确认词恰好是「删除」才允许提交", () => {
    expect(deleteBlockReason(DELETE_READY)).toBeNull();
    expect(canSubmitDelete(DELETE_READY)).toBe(true);
  });

  it("判据顺序：空组优先于确认词错误", () => {
    const input = { ...DELETE_READY, txnCount: 0, confirmPhrase: "" };
    expect(deleteBlockReason(input)).toBe("该组没有可处理的交易");
  });

  it("判据顺序：预览未返回优先于确认词错误", () => {
    const input = { ...DELETE_READY, preview: null, confirmPhrase: "" };
    expect(deleteBlockReason(input)).toBe("请先查看影响");
  });
});
