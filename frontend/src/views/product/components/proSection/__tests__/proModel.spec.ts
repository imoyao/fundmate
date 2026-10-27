import { describe, expect, it } from "vitest";
import type { ProStatusResult } from "@/api/products";
import {
  MODULE_META,
  PRO_ASSET_TYPES,
  badgeText,
  isEntitled,
  isProEnabled,
  liveModuleCount,
  moduleAvailable,
  nextPendingModule,
  progressText
} from "../proModel";

type Mod = { available: boolean; phase: number };

const mod = (available: boolean, phase = 1): Mod => ({ available, phase });

const status = (
  over: {
    paywall_required?: boolean;
    modules?: Record<string, Mod>;
  } = {}
): ProStatusResult =>
  ({
    paywall_required: true,
    modules: {
      performance: mod(false, 2),
      risk: mod(false, 3),
      allocation: mod(false, 4),
      report: mod(false, 5),
      ...over.modules
    },
    ...over
  }) as unknown as ProStatusResult;

describe("品类门控", () => {
  it("只对基金家族渲染", () => {
    expect(PRO_ASSET_TYPES).toEqual(["fund", "etf"]);
    expect(isProEnabled("fund")).toBe(true);
    expect(isProEnabled("etf")).toBe(true);
  });

  it("其余品类与缺失一律不渲染（不猜）", () => {
    expect(isProEnabled("stock")).toBe(false);
    expect(isProEnabled("manager")).toBe(false);
    expect(isProEnabled(null)).toBe(false);
    expect(isProEnabled(undefined)).toBe(false);
  });
});

describe("moduleAvailable / badgeText", () => {
  it("状态位未就绪按未上线处理，且不编造徽标", () => {
    expect(moduleAvailable(null, "performance")).toBe(false);
    expect(badgeText(null, "performance")).toBeNull();
  });

  it("模块缺键时不渲染徽标", () => {
    const s = status({ modules: {} });
    expect(badgeText(s, "performance")).toBeNull();
  });

  it("已上线给「已上线」，未上线给 Phase 文案", () => {
    const s = status({
      modules: { performance: mod(true), risk: mod(false, 3) }
    });
    expect(badgeText(s, "performance")).toBe("已上线");
    expect(badgeText(s, "risk")).toBe("Phase 3 建设中");
  });
});

describe("isEntitled：只认后端权益事实", () => {
  it("paywall_required=false 才算已开通", () => {
    expect(isEntitled(status({ paywall_required: false }))).toBe(true);
    expect(isEntitled(status({ paywall_required: true }))).toBe(false);
  });

  it("状态位取不到按未开通（介绍卡是兜底内容，不能把区块掏空）", () => {
    expect(isEntitled(null)).toBe(false);
  });
});

describe("liveModuleCount / nextPendingModule", () => {
  it("计数只数 available===true 的模块", () => {
    expect(liveModuleCount(null)).toBe(0);
    expect(
      liveModuleCount(
        status({ modules: { performance: mod(true), risk: mod(true) } })
      )
    ).toBe(2);
  });

  it("下一个在建模块按 MODULE_META 顺序取首个未上线项", () => {
    // performance 已上线 ⇒ 首个未上线是 risk（顺序不是后端键序）
    const s = status({
      modules: { performance: mod(true), risk: mod(false, 3) }
    });
    expect(nextPendingModule(s)).toEqual({
      title: "偏离与风险控制",
      phase: 3
    });
  });

  it("全上线返回 null（不硬凑「建设中」）", () => {
    const s = status({
      modules: {
        performance: mod(true),
        risk: mod(true),
        allocation: mod(true),
        report: mod(true)
      }
    });
    expect(liveModuleCount(s)).toBe(MODULE_META.length);
    expect(nextPendingModule(s)).toBeNull();
  });

  it("模块未上线但后端没给 phase ⇒ null（不编造阶段号）", () => {
    expect(nextPendingModule(status({ modules: {} }))).toBeNull();
  });
});

describe("progressText：整串在模型层拼", () => {
  it("有在建模块时带 · 与标题 Phase", () => {
    const s = status({
      modules: { performance: mod(true), risk: mod(false, 3) }
    });
    expect(progressText(s)).toBe(
      `已上线 1/${MODULE_META.length} · 偏离与风险控制 Phase 3 建设中`
    );
  });

  it("全上线只有计数", () => {
    const s = status({
      modules: {
        performance: mod(true),
        risk: mod(true),
        allocation: mod(true),
        report: mod(true)
      }
    });
    expect(progressText(s)).toBe(`已上线 4/${MODULE_META.length}`);
  });

  it("状态位缺失时不出现 undefined 字样", () => {
    expect(progressText(null)).toBe(`已上线 0/${MODULE_META.length}`);
  });
});
