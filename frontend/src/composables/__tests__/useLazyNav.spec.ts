/**
 * `useLazyNav`：跳转前先激活目标区块。
 *
 * 拆成 `createLazyNav(nav, registry)` 内核来测——`useLazyNav` 只负责 provide
 * 注册表，真正的契约（**先激活、后跳转**）在这里。node 环境无 DOM，故注册表
 * 直接注入，不经过组件树。
 *
 * 顺序为什么要钉：反了就是「跳到占位块上、内容随后长出来把页面顶下去」，用户
 * 看到的是位置漂移。这条顺序没有任何类型能表达，只能靠断言。
 */
import { describe, expect, it, vi } from "vitest";
import { createLazyNav } from "../useLazyNav";
import type { LazySectionRegistry } from "@/components/LazySection/registry";

function setup(registered: string[] = []) {
  const calls: string[] = [];
  const registry: LazySectionRegistry = new Map();
  for (const id of registered) {
    registry.set(id, () => calls.push(`activate:${id}`));
  }
  const nav = { goTo: vi.fn((id: string) => calls.push(`goTo:${id}`)) };
  const goTo = createLazyNav(nav, registry);
  return { goTo, calls, nav, registry };
}

describe("createLazyNav：跳转前激活懒加载区块", () => {
  it("已注册的区块：先激活内容，再跳转", () => {
    const { goTo, calls } = setup(["nav-calendar"]);
    goTo("nav-calendar");
    expect(calls).toEqual(["activate:nav-calendar", "goTo:nav-calendar"]);
  });

  it("未注册的锚点（非懒加载 / 常驻区块）：只跳转，不凭空激活", () => {
    const { goTo, calls, nav } = setup();
    goTo("nav-overview");
    expect(calls).toEqual(["goTo:nav-overview"]);
    expect(nav.goTo).toHaveBeenCalledWith("nav-overview");
  });

  it("注册表里有别的 id 时，只激活被点击的那一个", () => {
    const { goTo, calls } = setup(["nav-cycles", "nav-attribution"]);
    goTo("nav-attribution");
    expect(calls).toEqual(["activate:nav-attribution", "goTo:nav-attribution"]);
  });

  it("id 原样透传，不做前缀改写（锚点即 DOM id）", () => {
    const { goTo, nav } = setup(["nav-structure"]);
    goTo("nav-structure");
    expect(nav.goTo).toHaveBeenCalledWith("nav-structure");
  });
});
