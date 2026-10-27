/**
 * 导入结果页的两条显隐规则（#980 批 B3，自 ResultStep.vue 抽出）。
 *
 * ## 这个文件钉什么
 *
 * 规则本身只有几行布尔运算，但它们决定「用户看到的导入结论」，且两个计数
 * 容易记反：
 * - `keptBlocked`（勾选保留但被去重规则拦下 = **实际没入库**）同时进 ① 异常侧
 *   与 ② 补充说明；
 * - `kept`（按勾选**真的入库了**）只进 ②，不进 ①——它是好消息，不该让副文案
 *   变成「有异常」。
 * - `duplicate` / `error` 只进 ①：它们的明细由 ImportErrorSummary 展开，
 *   再进 ② 就是同一件事说两遍。
 *
 * ⚠️ 为什么测纯模块而不是挂载 ResultStep：vitest 环境是 node（无 DOM，仓库未装
 * @vue/test-utils），且 .vue 那条依赖链会拖起 element-plus / router。
 */
import { describe, expect, it } from "vitest";

import {
  hasAnomalies,
  hasSupplements,
  type ImportResultState
} from "../../importResultModel";

/** 全零基线：一切为 0 时两条规则都应为 false（空结果页不该出现任何卡片） */
function zero(): ImportResultState {
  return {
    skipped: 0,
    duplicate: 0,
    error: 0,
    orphan: 0,
    kept: 0,
    keptBlocked: 0,
    cashTransfers: 0,
    hasImportErrors: false,
    showPriceUpdateTip: false
  };
}

describe("hasAnomalies（副文案走「干净」分支与否）", () => {
  it("全零 → 无异常（显示「全部数据校验通过」）", () => {
    expect(hasAnomalies(zero())).toBe(false);
  });

  it("kept 单独存在不算异常（勾选保留是真的入库了，是好消息）", () => {
    expect(hasAnomalies({ ...zero(), kept: 3 })).toBe(false);
  });

  it("keptBlocked 单独存在就算异常（勾选保留但被去重规则拦下＝实际没入库）", () => {
    expect(hasAnomalies({ ...zero(), keptBlocked: 1 })).toBe(true);
  });

  it.each([
    ["skipped", { skipped: 1 }],
    ["duplicate", { duplicate: 2 }],
    ["error", { error: 1 }],
    ["orphan", { orphan: 1 }]
  ])("%s 单独存在就算异常", (_label, patch) => {
    expect(hasAnomalies({ ...zero(), ...patch })).toBe(true);
  });

  it("补充信息类开关不影响异常判定（价格提示 / 转账不是「异常」）", () => {
    expect(
      hasAnomalies({
        ...zero(),
        showPriceUpdateTip: true,
        cashTransfers: 2,
        hasImportErrors: false
      })
    ).toBe(false);
  });
});

describe("hasSupplements（补充信息区块是否出现）", () => {
  it("全零 → 不出现（否则会渲染出一条孤零零的上边框）", () => {
    expect(hasSupplements(zero())).toBe(false);
  });

  it.each([
    ["cashTransfers", { cashTransfers: 1 }],
    ["kept", { kept: 1 }],
    ["keptBlocked", { keptBlocked: 1 }],
    ["orphan", { orphan: 1 }],
    ["hasImportErrors", { hasImportErrors: true }],
    ["showPriceUpdateTip", { showPriceUpdateTip: true }]
  ])("%s 单独存在就出现", (_label, patch) => {
    expect(hasSupplements({ ...zero(), ...patch })).toBe(true);
  });

  it("duplicate / error 单独存在不触发区块（明细由 ImportErrorSummary 展开，不重复说）", () => {
    expect(hasSupplements({ ...zero(), duplicate: 2, error: 1 })).toBe(false);
    // 但真的带了错误明细时仍然出现
    expect(
      hasSupplements({
        ...zero(),
        duplicate: 2,
        error: 1,
        hasImportErrors: true
      })
    ).toBe(true);
  });

  it("skipped 单独存在不触发区块（只体现在副文案的「N 笔跳过」）", () => {
    expect(hasSupplements({ ...zero(), skipped: 5 })).toBe(false);
  });
});
