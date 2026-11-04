/**
 * 「添加自选」行三列取值单测（#980 拆分时新增）。
 *
 * 为什么值得单测：这段逻辑原本是组件内两个闭包（`rowColumns` / `venueLabelOf`），
 * 改错的唯一表现是「下拉里的灰字不对」——没有判据，只能靠肉眼。拆成纯函数后可以钉住三件事：
 *
 * 1. **组合类标的绝不出现平台原生码**（且慢 ZHxxxx / 天天基金 tgCode / MGR_ 派生码）。
 *    这是 @/constants/advisorPlatform 的硬约束，也是历史上最容易被「顺手展示编码」破的约束。
 * 2. **缺失值不渲染空壳**：`sub` 该是 undefined，而不是空串或「·」残渣。
 * 3. **无市场实体的标的不展示场所标签**（`venueLabelOf` 返回空串 → 模板 v-if 不渲染）。
 *
 * 已知债：`@/utils/assetDisplay` 的 buildAssetSubtitle 是同口径的单一真相源，
 * 本模块尚未收口（见 assetOptionColumns.ts 头部注释）。若哪天收口，本 spec 应随之迁移，
 * 但断言口径不变——上面三条与实现放在哪个文件无关。
 */
import { describe, it, expect } from "vitest";
import { rowColumns, typeLabelOf, venueLabelOf } from "../assetOptionColumns";
import type { SearchAssetOption } from "../assetOptionColumns";
import { getTypeLabel } from "@/constants/assetType";

const base = (over: Partial<SearchAssetOption> = {}): SearchAssetOption => ({
  symbol: "159915",
  name: "创业板ETF",
  market: "SZ",
  type: "etf",
  venue: "EXCHANGE",
  ...over
});

describe("rowColumns", () => {
  it("带编码品种：名称 | 编码 | 类型，typeKey 原样透传", () => {
    const row = rowColumns(base());
    expect(row.name).toBe("创业板ETF");
    expect(row.sub).toBe("159915");
    expect(row.type).toBe(getTypeLabel("etf"));
    expect(row.typeKey).toBe("etf");
  });

  it("投顾组合：次要锚点是「平台 · 主理人」，且不含平台原生码", () => {
    const row = rowColumns(
      base({
        symbol: "ZH123456",
        name: "长赢指数投资",
        type: "portfolio",
        venue: "",
        extra: { platform: "QIEMAN", host: "银行螺丝钉" }
      })
    );
    expect(row.sub).toBe("且慢 · 银行螺丝钉");
    // 平台原生码对用户无意义：ZH 开头那段不能出现在任何一列
    expect(JSON.stringify(row)).not.toContain("ZH123456");
  });

  it("投顾组合：缺主理人时只剩平台，不残留分隔符", () => {
    const row = rowColumns(
      base({
        type: "portfolio",
        venue: "",
        extra: { platform: "TIANTIAN" }
      })
    );
    expect(row.sub).toBe("天天基金");
    expect(row.sub).not.toContain("·");
  });

  it("基金经理：次要锚点是所属公司，不展示 MGR_ 派生码", () => {
    const row = rowColumns(
      base({
        symbol: "MGR_0001",
        name: "张三",
        type: "manager",
        venue: "",
        extra: { company: "易方达基金" }
      })
    );
    expect(row.sub).toBe("易方达基金");
    expect(JSON.stringify(row)).not.toContain("MGR_0001");
  });

  it("组合类缺 extra：sub 为 undefined（不渲染空灰字）", () => {
    const row = rowColumns(base({ type: "portfolio", venue: "" }));
    expect(row.sub).toBeUndefined();
  });

  it("普通标的空编码：sub 为 undefined，而不是空串", () => {
    const row = rowColumns(base({ symbol: "" }));
    expect(row.sub).toBeUndefined();
  });
});

describe("typeLabelOf / venueLabelOf", () => {
  it("品类走中文映射，未知品类原样兜底", () => {
    expect(typeLabelOf(base({ type: "money_fund" }))).toBe(
      getTypeLabel("money_fund")
    );
    expect(typeLabelOf(base({ type: "unknown_type" }))).toBe("unknown_type");
  });

  it("空 venue 返回空串（模板据此不渲染场所标签）", () => {
    expect(venueLabelOf(base({ venue: "" }))).toBe("");
  });

  it("场所走中文映射：场内 / 场外，未知值原样兜底", () => {
    expect(venueLabelOf(base({ venue: "EXCHANGE" }))).toBe("场内");
    expect(venueLabelOf(base({ venue: "OTC" }))).toBe("场外");
    expect(venueLabelOf(base({ venue: "WEIRD" }))).toBe("WEIRD");
  });
});
