/**
 * 覆盖率作用域提示（#2595 验收第 3 条）。
 *
 * 钉三件事：
 * - 家庭级不提示（它是基准线本身）；
 * - 账户档与组合档**说的不是同一句话**（复用一句会把「账户之间不可比」说成组合级）；
 * - 文案里不写死具体百分比（如「上限 53%」是本机某次实测值，会随持仓结构漂移）。
 */
import { describe, it, expect } from "vitest";
import { coverageScopeNote } from "../coverageNote";

describe("coverageScopeNote：覆盖率作用域提示", () => {
  it("家庭级不提示", () => {
    expect(coverageScopeNote("family")).toBe("");
  });

  it("scope 缺失（旧响应 / 未加载）时不猜作用域", () => {
    // 猜错会把「账户级覆盖率高」说成需要提醒，比不说更糟
    expect(coverageScopeNote(undefined)).toBe("");
  });

  it("账户级：明说「不可直接比大小」，而不只是「会波动」", () => {
    const note = coverageScopeNote("ledger");

    expect(note).toContain("账户");
    expect(note).toContain("不可直接比大小");
    // 同时保留「为什么」：硬上限的三个成因不能只字不提
    expect(note).toContain("ETF");
  });

  it("组合级：说的是组合归属口径，不是账户拆分", () => {
    const note = coverageScopeNote("portfolio");

    expect(note).toContain("组合");
    expect(note).toContain("不可直接比大小");
    expect(note).not.toContain("账户拆开");
  });

  it("两档文案不同（复用同一句会让组合级读成账户级）", () => {
    expect(coverageScopeNote("ledger")).not.toBe(
      coverageScopeNote("portfolio")
    );
  });

  it("不写死具体百分比：那是会漂移的实测值，不该变成常驻断言", () => {
    expect(coverageScopeNote("ledger")).not.toMatch(/\d+(\.\d+)?%/);
    expect(coverageScopeNote("portfolio")).not.toMatch(/\d+(\.\d+)?%/);
  });
});
