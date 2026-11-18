/**
 * 缺账本流水回填弹窗的提交准入单测（#2875）。
 *
 * 钉住三件会让「显式、安全的回填」失效的事：
 *   ① 组里含任一 blocked 流水（组级或逐条）仍允许提交；
 *   ② 没展开看逐条归属 / 没勾二次确认就允许提交；
 *   ③ 提交进行中允许重复提交。
 * 断言落在**具体原因文案**上（Vue 子组件 render 抛错时 DOM 冻结末次成功渲染，
 * 只数锚点会假绿）。
 */
import { describe, expect, it } from "vitest";
import {
  canSubmitOrphanBackfill,
  submitBlockReason,
  type OrphanLedgerSubmitInput
} from "../orphanLedgerFixGuard";

/** 一份「可回填、已看过明细、已勾选」的基准输入 */
const READY: OrphanLedgerSubmitInput = {
  group: {
    block_reason: null,
    transactions: [{ block_reason: null }, { block_reason: null }]
  },
  previewSeen: true,
  confirmed: true,
  submitting: false
};

describe("缺账本流水回填的提交准入（#2875）", () => {
  it("全部条件满足才允许提交", () => {
    expect(submitBlockReason(READY)).toBeNull();
    expect(canSubmitOrphanBackfill(READY)).toBe(true);
  });

  it("未选择分组时不许提交", () => {
    const input = { ...READY, group: null };
    expect(submitBlockReason(input)).toBe("未选择待回填分组");
    expect(canSubmitOrphanBackfill(input)).toBe(false);
  });

  it("组级 block_reason 非空时整体拒绝（blocked 组不给试）", () => {
    const input = {
      ...READY,
      group: {
        block_reason: "多笔流水无法唯一归属账本",
        transactions: [{ block_reason: null }]
      }
    };
    expect(submitBlockReason(input)).toBe("该组含无法唯一归属的流水，不能回填");
    expect(canSubmitOrphanBackfill(input)).toBe(false);
  });

  it("组级原因为 null 但逐条有 blocked 时同样拒绝（不能只信组级概括）", () => {
    const input = {
      ...READY,
      group: {
        block_reason: null,
        transactions: [
          { block_reason: null },
          { block_reason: "account_name 为空，无法归属" }
        ]
      }
    };
    expect(submitBlockReason(input)).toBe("该组含无法唯一归属的流水，不能回填");
    expect(canSubmitOrphanBackfill(input)).toBe(false);
  });

  it("空组（0 条流水）即使已确认也不许提交空请求", () => {
    const input = {
      ...READY,
      group: { block_reason: null, transactions: [] }
    };
    // 空组本身不含 blocked，容易被 some() 的 false 放行；
    // 这里钉住：后端 _normalize_ids 会拒绝空列表，前端也不该放行。
    expect(submitBlockReason(input)).toBe("该组没有可回填的流水");
    expect(canSubmitOrphanBackfill(input)).toBe(false);
  });

  it("提交进行中不允许重复提交", () => {
    const input = { ...READY, submitting: true };
    expect(submitBlockReason(input)).toBe("正在提交回填");
    expect(canSubmitOrphanBackfill(input)).toBe(false);
  });

  it("没展开看逐条归属时不许提交", () => {
    const input = { ...READY, previewSeen: false };
    expect(submitBlockReason(input)).toBe("请先展开查看逐条归属");
    expect(canSubmitOrphanBackfill(input)).toBe(false);
  });

  it("没勾二次确认时不许提交", () => {
    const input = { ...READY, confirmed: false };
    expect(submitBlockReason(input)).toBe("请勾选确认后再回填");
    expect(canSubmitOrphanBackfill(input)).toBe(false);
  });

  it("优先级：blocked 组即使其它条件全满足，原因仍是「不能回填」", () => {
    const input = {
      ...READY,
      group: {
        block_reason: null,
        transactions: [{ block_reason: "同 family 下无名为 X 的账本" }]
      },
      previewSeen: false,
      confirmed: false,
      submitting: true
    };
    expect(submitBlockReason(input)).toBe("该组含无法唯一归属的流水，不能回填");
  });
});
