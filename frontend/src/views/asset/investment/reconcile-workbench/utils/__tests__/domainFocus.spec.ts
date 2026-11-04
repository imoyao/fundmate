/**
 * 对账中心横幅「跳到第一个有待办的域」的选域规则（#1259，自 index.vue 抽出）。
 *
 * ## 这个文件钉什么
 *
 * 1. **固定优先级**：B → C → A → D → E。用户点横幅是想「开始处理」，固定顺序
 *    保证同一页面状态下每次点击落在同一个域；若改成「取待处理数最大的域」，
 *    忽略一条之后落点就会在几个域之间来回跳。
 * 2. **全零返回 null**：没有待办时调用方不该切域（原实现 `if (!target) return`）。
 * 3. **相等也算 0**：只有 > 0 才算待办。
 */
import { describe, expect, it } from "vitest";

import { DOMAIN_FOCUS_ORDER, pickFirstPendingDomain } from "../domainFocus";
import type { WorkbenchDomainKey } from "../../constants/domainTabs";

/** 用一张表构造 pending 取数函数，未列出的域一律 0 */
function pendingFrom(map: Partial<Record<WorkbenchDomainKey, number>>) {
  return (key: WorkbenchDomainKey) => map[key] ?? 0;
}

describe("pickFirstPendingDomain", () => {
  it("优先级固定为 B → C → A → D → E", () => {
    expect([...DOMAIN_FOCUS_ORDER]).toEqual(["B", "C", "A", "D", "E"]);
  });

  it("多个域都有待办时取优先级最高的那个，而不是数最大的", () => {
    // E 有 99 项，但 B 的优先级更高
    expect(pickFirstPendingDomain(pendingFrom({ E: 99, B: 1 }))).toBe("B");
    // B 没了才轮到 C，哪怕 A 的数更大
    expect(pickFirstPendingDomain(pendingFrom({ A: 50, C: 2 }))).toBe("C");
  });

  it("跳过待处理数为 0 的域", () => {
    expect(pickFirstPendingDomain(pendingFrom({ B: 0, C: 3 }))).toBe("C");
  });

  it("全部为 0 → null（调用方据此不切域）", () => {
    expect(pickFirstPendingDomain(pendingFrom({}))).toBeNull();
  });

  it("负数视为无待办（后端不该返回，但别把它当命中）", () => {
    expect(pickFirstPendingDomain(pendingFrom({ B: -1, D: 1 }))).toBe("D");
  });

  it("接受注入的优先级（测试可换顺序，默认顺序不变）", () => {
    const reversed: WorkbenchDomainKey[] = ["E", "D", "C", "B", "A"];
    expect(pickFirstPendingDomain(pendingFrom({ B: 1, E: 1 }), reversed)).toBe(
      "E"
    );
  });
});
