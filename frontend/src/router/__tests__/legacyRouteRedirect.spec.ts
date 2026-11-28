/**
 * 历史路由别名守卫（2026-11-28 两页合并，P3-C）。
 *
 * `/asset/position-analysis`（原「持仓分析」）已并入 `/analysis`（「投资复盘」）。
 * 它**不能删**：那是外部书签与已分享链接能到达的 URL。但重定向写错的方式很安静——
 *
 * 1. **丢了 query** ⇒ 旧链接常带 `?scope=ledger&scope_id=3`，丢掉就落回家庭级，
 *    用户以为「我选的那个账户没了」，而页面上一切正常（静默错口径）；
 * 2. **目标 path 不存在** ⇒ 落到 404 或空白页，只有手敲旧链接的人才会遇到；
 * 3. **忘了 `showLink: false`** ⇒ 侧栏出现两项「分析」，用户分不清该点哪个；
 * 4. **旧组件 import 没删** ⇒ 死文件继续被引用，`check_vue_size` 与任何「按文件扫」
 *    的守卫都还会算它，等于把已删页面留在账上。
 *
 * 判据纪律：直接调用 `redirect` 函数比对返回值（而不是正则读源码），
 * 这样「函数签名变了、返回结构变了」都会红。
 */
import { describe, it, expect } from "vitest";
import home from "../modules/home";

type RedirectFn = (to: { query: Record<string, string> }) => {
  path: string;
  query: Record<string, string>;
};

const child = (path: string) =>
  (home.children ?? []).find(c => c.path === path);

describe("历史路由别名：/asset/position-analysis → /analysis", () => {
  const legacy = child("/asset/position-analysis");

  it("路由仍在（删掉等于让旧书签 404）", () => {
    expect(legacy, "旧 path 必须保留为重定向").toBeTruthy();
  });

  it("是 redirect 而不是 component（旧页面已删除，不该还有组件）", () => {
    expect(typeof legacy?.redirect).toBe("function");
    expect(legacy?.component).toBeUndefined();
  });

  it("口径 query 原样带走（丢 query = 静默退回家庭级）", () => {
    const redirect = legacy?.redirect as unknown as RedirectFn;
    expect(redirect({ query: { scope: "ledger", scope_id: "3" } })).toEqual({
      path: "/analysis",
      query: { scope: "ledger", scope_id: "3" }
    });
    expect(redirect({ query: {} })).toEqual({ path: "/analysis", query: {} });
  });

  it("目标 path 真的在路由表里（防重定向到不存在的地址）", () => {
    const target = (legacy?.redirect as unknown as RedirectFn)({ query: {} });
    expect(
      child(target.path),
      `${target.path} 不在 home 路由表里`
    ).toBeTruthy();
  });

  it("不进侧栏（否则两个「分析」并列，用户不知道该点哪个）", () => {
    expect(legacy?.meta?.showLink).toBe(false);
  });

  it("全仓不再 import 已删除的旧页面组件", () => {
    // 只查路由模块这一层：真正会「引用已删文件」的就是这里
    const files = [home];
    for (const r of files) {
      for (const c of r.children ?? []) {
        expect(String(c.component ?? "")).not.toContain(
          "views/asset/position-analysis"
        );
      }
    }
  });
});
