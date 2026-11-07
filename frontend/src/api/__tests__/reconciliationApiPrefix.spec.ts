import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * #2866 实测事故：api/reconciliation.ts 的 12 个端点漏写 `/api` 前缀，
 * vite 只代理 `/api`，未知路径会走 SPA 回退返回 index.html（HTTP 200）。
 * 前端把 HTML 当数据，字段全 undefined → 「0 条 + 空态」，且不抛错、catch 不触发；
 * e2e 用 page.route 桩拦旧路径所以一路全绿，真实页面却整页空。
 *
 * 这条用例直接读源码字符串，不依赖任何桩：桩能骗过渲染断言，骗不过源码本身。
 */
const source = readFileSync(
  new URL("../reconciliation.ts", import.meta.url),
  "utf8"
);

/** 源码里所有形如 "/xxx/" 的字符串字面量（API 路径） */
const literalPaths = Array.from(
  source.matchAll(/"(\/[a-z][a-z0-9/_.-]*)"/g),
  m => m[1]
);

describe("对账接口路径前缀（#2866 防回潮）", () => {
  it("至少覆盖 12 个对账端点，避免集合为空导致恒真", () => {
    const apiPaths = literalPaths.filter(p => p.includes("/reconciliation/"));
    expect(apiPaths.length).toBeGreaterThanOrEqual(12);
  });

  it("不存在漏写 /api 的对账路径", () => {
    expect(literalPaths.filter(p => p.startsWith("/reconciliation/"))).toEqual(
      []
    );
  });

  it("所有对账端点都以 /api/ 开头", () => {
    const apiPaths = literalPaths.filter(p => p.includes("/reconciliation/"));
    for (const p of apiPaths) {
      expect(p.startsWith("/api/")).toBe(true);
    }
  });
});
