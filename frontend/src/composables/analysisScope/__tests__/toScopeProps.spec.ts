/**
 * 口径 → 面板 props / 接口参数的翻译（#2595 / #3287）。
 *
 * 钉的是**「不该传的时候一个都不能传」**，而不是「传对了」——#2595 的事故形态是
 * 「组合详情页复用时漏传 scope，安静显示家庭级数据」，反向的错误是「切回家族档
 * 还带着上次的 ledgerId」。两者都不报错，只能靠单测钉。
 */
import { describe, it, expect } from "vitest";
import { toScopeProps, toScopeQuery } from "../toScopeProps";

describe("toScopeProps：三级口径翻译", () => {
  it("账户档 + 已选账户 → 只传 ledgerId", () => {
    const props = toScopeProps("ledger", 3);

    expect(props).toEqual({ ledgerId: 3 });
    // 互斥是后端硬约束（同时传 = 400），前端不许两个一起给
    expect("portfolioId" in props).toBe(false);
  });

  it("组合档 + 已选组合 → 只传 portfolioId", () => {
    const props = toScopeProps("portfolio", 7);

    expect(props).toEqual({ portfolioId: 7 });
    expect("ledgerId" in props).toBe(false);
  });

  it("家庭档 → 空对象（不是 { ledgerId: null }）", () => {
    const props = toScopeProps("family", null);

    // `null` 会被面板当成「显式传了空作用域」，与「不传」语义不同
    expect(props).toEqual({});
    expect(Object.keys(props)).toHaveLength(0);
  });

  it("切回家族档但残留 id 时，仍然不传任何作用域", () => {
    // 切换器的 watch 会清 id，但清之前的一帧里可能还在——这里兜住「脏 id 不外泄」
    expect(toScopeProps("family", 42)).toEqual({});
  });

  it("账户档 / 组合档但尚未选对象 → 空对象（不传 undefined 之外的脏值）", () => {
    expect(toScopeProps("ledger", null)).toEqual({});
    expect(toScopeProps("portfolio", undefined)).toEqual({});
  });
});

describe("toScopeQuery：接口参数翻译", () => {
  it("账户档 + 已选账户 → scope=ledger 且带 ledger_id", () => {
    expect(toScopeQuery("ledger", 3)).toEqual({
      scope: "ledger",
      ledger_id: 3
    });
  });

  it("组合档 + 已选组合 → scope=portfolio 且带 portfolio_id", () => {
    expect(toScopeQuery("portfolio", 7)).toEqual({
      scope: "portfolio",
      portfolio_id: 7
    });
  });

  it("家庭档 → 显式 scope=family，且一个 id 都不带", () => {
    // 不能靠「两个 id 都不传」让后端推断：cash-flow 等端点对缺参会 400，
    // 而另一些端点会安静退回家庭级 —— 两种都不是可接受的隐式行为
    const query = toScopeQuery("family", null);

    expect(query).toEqual({ scope: "family" });
    expect("ledger_id" in query).toBe(false);
    expect("portfolio_id" in query).toBe(false);
  });

  it("切档但尚未选对象 → 只发 scope，不带任何 id", () => {
    // 此时调用方本不该取数（isReady=false）。真发了也只会被后端 400 拦下，
    // 不会像「悄悄退回家庭级」那样错得看不出来。
    expect(toScopeQuery("ledger", null)).toEqual({ scope: "ledger" });
    expect(toScopeQuery("portfolio", undefined)).toEqual({
      scope: "portfolio"
    });
  });

  it("家庭档残留 id → 仍然只发 scope=family（脏 id 不外泄）", () => {
    expect(toScopeQuery("family", 42)).toEqual({ scope: "family" });
  });
});
