// frontend/src/utils/__tests__/productIdentity.spec.ts
//
// #2006 回归样本：详情页 URL 不承载 `market` / `venue` 消歧参数。
//
// 背景：这两个参数从前由 `productRoute` 拼进 query，而 `parseProductRef` 的
// 对象形式只读 `route.params`（路由 `/:assetType/:symbol` 没有对应参数位），
// 于是「写了没人读」。取证确认库内无同码多实体后按「URL 不承载消歧参数」收敛，
// 这组用例把这个结论钉住——将来谁想加回来，先看这里为什么要删。
import { describe, expect, it } from "vitest";
import { parseProductRef, productRoute } from "../productIdentity";

describe("productRoute", () => {
  it("只产出品类段 + symbol", () => {
    expect(productRoute({ assetType: "stock", symbol: "SH601899" })).toBe(
      "/stock/SH601899"
    );
    expect(productRoute({ assetType: "fund", symbol: "004369" })).toBe(
      "/fund/004369"
    );
  });

  it("URL 里不出现 ? / market / venue（消歧参数不再经 URL 传递）", () => {
    const url = productRoute({ assetType: "stock", symbol: "SZ000001" });

    expect(url).not.toContain("?");
    expect(url).not.toContain("market");
    expect(url).not.toContain("venue");
  });

  it("品类段不在白名单、或 symbol 为空 → 空串（调用方据此回退）", () => {
    // index 至今未开放（#2028 卡在 #1407 估值长历史口径），故拿它当「不在白名单」的样本
    expect(productRoute({ assetType: "index", symbol: "000300" })).toBe("");
    expect(productRoute({ assetType: "stock", symbol: "  " })).toBe("");
  });

  it("etf 自 #1974 起产出 /etf/ 路径段，不套 /fund/", () => {
    // ETF 是场内证券、落 securities 表，与场外基金不同口径——URL 必须能区分二者
    expect(productRoute({ assetType: "etf", symbol: "SZ159915" })).toBe(
      "/etf/SZ159915"
    );
  });

  it("symbol 只编码一次（含特殊字符的代码不被中途改写）", () => {
    expect(productRoute({ assetType: "stock", symbol: "A B" })).toBe(
      "/stock/A%20B"
    );
  });
});

describe("parseProductRef", () => {
  it("对象形式（vue-router route）只读 params", () => {
    expect(
      parseProductRef({ params: { assetType: "fund", symbol: "004369" } })
    ).toEqual({ assetType: "fund", symbol: "004369" });
  });

  it("字符串形式解析裸 path", () => {
    expect(parseProductRef("/stock/SH601899")).toEqual({
      assetType: "stock",
      symbol: "SH601899"
    });
  });

  it("忽略 query：带 ?market=&venue= 也不再解析出来（死链清理）", () => {
    const ref = parseProductRef("/stock/SH601899?market=CN_A&venue=EXCHANGE");

    expect(ref).toEqual({ assetType: "stock", symbol: "SH601899" });
    expect(ref).not.toHaveProperty("market");
    expect(ref).not.toHaveProperty("venue");
  });

  it("返回值里没有 market / venue 字段（本卡行为锁）", () => {
    const ref = parseProductRef("/fund/004369");

    expect(ref).not.toBeNull();
    expect(Object.keys(ref ?? {}).sort()).toEqual(["assetType", "symbol"]);
  });

  it("品类段非白名单 / 缺 symbol / 输入为空 → null", () => {
    expect(parseProductRef("/index/000300")).toBeNull();
    expect(parseProductRef("/stock/")).toBeNull();
    expect(parseProductRef("")).toBeNull();
    expect(parseProductRef(undefined)).toBeNull();
  });

  it("etf 路径段可解析（#1974 开放，与 productRoute 往返一致）", () => {
    expect(parseProductRef("/etf/SZ159915")).toEqual({
      assetType: "etf",
      symbol: "SZ159915"
    });
  });

  it("symbol 只解码一次", () => {
    expect(parseProductRef("/stock/A%20B")).toEqual({
      assetType: "stock",
      symbol: "A B"
    });
  });

  it("与 productRoute 互为逆运算（往返一致）", () => {
    const ref = { assetType: "stock", symbol: "SH601899" };

    expect(parseProductRef(productRoute(ref))).toEqual(ref);
  });
});
