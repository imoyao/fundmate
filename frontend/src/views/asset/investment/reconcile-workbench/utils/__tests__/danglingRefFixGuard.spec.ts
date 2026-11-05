/**
 * 悬空引用回补弹窗的提交准入单测（#2866）。
 *
 * 钉住两件会让「显式、安全地二次回补」失效的事：
 *   ① 预览未返回 / 预览进行中 / 提交进行中就允许提交（用户没看清影响就写了库）；
 *   ② 误把 safe=false 当成提交闸门——挂回只改 position_id、不动份额，safe=false
 *      （净额不自洽 / symbol 不一致）仍应允许提交，风险由预览面板 warning 告知。
 * 断言落在**具体原因文案**上，而不只是「按钮 disabled 属性存在」——Vue 子组件
 * render 抛错时 DOM 会冻结在末次成功渲染，只数锚点会假绿。
 */
import { describe, expect, it } from "vitest";
import {
  canSubmitReattach,
  submitBlockReason,
  type ReattachSubmitInput
} from "../danglingRefFixGuard";

/** 一份「已看过预览、可提交」的基准输入 */
const READY: ReattachSubmitInput = {
  preview: { safe: true },
  targetSelected: true,
  previewing: false,
  submitting: false
};

describe("悬空引用回补的提交准入（#2866）", () => {
  it("预览未返回前不允许提交，原因写清「请先查看影响预览」", () => {
    const input = { ...READY, preview: null };
    expect(submitBlockReason(input)).toBe("请先查看影响预览");
    expect(canSubmitReattach(input)).toBe(false);
  });

  it("预览请求进行中也不允许提交（预览尚未落地就写库）", () => {
    const input = { ...READY, preview: null, previewing: true };
    expect(submitBlockReason(input)).toBe("正在预览影响");
    expect(canSubmitReattach(input)).toBe(false);
  });

  it("预览刷新中即使还留着旧预览也不许提交", () => {
    const input = { ...READY, previewing: true };
    expect(submitBlockReason(input)).toBe("正在预览影响");
    expect(canSubmitReattach(input)).toBe(false);
  });

  it("提交进行中不允许重复提交", () => {
    const input = { ...READY, submitting: true };
    expect(submitBlockReason(input)).toBe("正在提交回补");
    expect(canSubmitReattach(input)).toBe(false);
  });

  it("safe=false 仍允许提交（只改指针不动份额，风险由预览 warning 告知）", () => {
    const input = { ...READY, preview: { safe: false } };
    expect(submitBlockReason(input)).toBeNull();
    expect(canSubmitReattach(input)).toBe(true);
  });

  it("预览已返回且 safe=true、目标已选，才允许提交", () => {
    expect(submitBlockReason(READY)).toBeNull();
    expect(canSubmitReattach(READY)).toBe(true);
  });

  it("未选目标持仓时不允许提交", () => {
    const input = { ...READY, targetSelected: false };
    expect(submitBlockReason(input)).toBe("未选择目标持仓");
    expect(canSubmitReattach(input)).toBe(false);
  });
});
