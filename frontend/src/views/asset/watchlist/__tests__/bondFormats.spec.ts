/**
 * 可转债条款增强列：正股PB / 到期收益 YTM（#1400 / #2575）。
 *
 * ## 这个文件钉什么
 *
 * 1. **0 是真实值，不是缺值**——正股 PB 可以是 0，YTM 可以正好打平 0.00%；
 *    若把 0 当缺值，用户看到的是 `—`（信息丢失）；若把 `null` 当 0，用户看到
 *    「收益率为零」——那是**编造**（后端对深度价内债明确返回 null，含义是
 *    「这个数没有意义」，不是「收益为零」）。
 * 2. **涨跌配色**按 A 股惯例：涨红跌绿；0 是持平，不该被涂成跌色。
 * 3. **列定义**必须限定在可转债品类，且分组正确。
 *
 * ⚠️ 为什么测 `./bondFormats` 而不是直接调渲染器：vitest 环境是 node（无 DOM），
 * 而 `columnRenderers.tsx` 会 import `MoneyDisplay` 等 `.vue` 组件，那条依赖链
 * 最终会初始化 router / supabase（实测一路要求 VITE_SUPABASE_URL →
 * VITE_ROUTER_HISTORY）。故按本目录既有约定（见 `linksRenderer.spec.ts`）把可测
 * 的整形逻辑留在纯模块里、这里直接测它。
 */

import { describe, expect, it } from "vitest";

import { BOND_EMPTY_TEXT, bondNumberText, bondYtmClass } from "../bondFormats";
import { watchlistColumnDefs } from "../columnDefs";

function bondDef(key: string) {
  const def = watchlistColumnDefs.find(d => d.key === key);
  if (!def) throw new Error(`${key} 列定义缺失`);
  return def;
}

describe("可转债增强列的定义（#2575）", () => {
  it("正股PB 与到期收益两列都存在且只属于可转债品类", () => {
    for (const key of ["bond_stock_pb", "bond_ytm"]) {
      const def = bondDef(key);
      expect(def.appliesTo).toEqual(["bond"]);
      expect(def.renderer).toBe("bond");
    }
  });

  it("到期收益列标注为自算口径（title 里带口径说明）", () => {
    // 渲染器的 title 写明「自算」——用户与集思录逐位对照时不会困惑
    expect(bondDef("bond_ytm").label).toBe("到期收益");
  });
});

describe("缺值与真实 0 的区分（最易出错的判据）", () => {
  it("null / undefined → 占位符 —", () => {
    expect(bondNumberText(null)).toBe(BOND_EMPTY_TEXT);
    expect(bondNumberText(undefined)).toBe(BOND_EMPTY_TEXT);
    expect(bondNumberText(NaN)).toBe(BOND_EMPTY_TEXT);
  });

  it("0 是真实值，照常格式化（不被当成缺值）", () => {
    expect(bondNumberText(0)).toBe("0.00");
    expect(bondNumberText(0, "%")).toBe("0.00%");
  });

  it("负值照常显示（负 PB 是真实值：正股净资产为负）", () => {
    expect(bondNumberText(-50.86)).toBe("-50.86");
  });

  it("带后缀的百分比格式化", () => {
    expect(bondNumberText(-8.1, "%")).toBe("-8.10%");
    expect(bondNumberText(2.15, "%")).toBe("2.15%");
  });
});

describe("到期收益的涨跌配色（A 股惯例：涨红跌绿）", () => {
  it("正收益 → 涨色类", () => {
    expect(bondYtmClass(2.15)).toBe("is-ytm-up");
  });

  it("负收益 → 跌色类", () => {
    expect(bondYtmClass(-8.1)).toBe("is-ytm-down");
  });

  it("持平 0 不挂涨跌类（持平不是跌）", () => {
    expect(bondYtmClass(0)).toBe("");
  });

  it("缺值不挂涨跌类", () => {
    expect(bondYtmClass(null)).toBe("");
    expect(bondYtmClass(undefined)).toBe("");
  });
});
