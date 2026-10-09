// frontend/src/utils/__tests__/bondExternalLinks.spec.ts
/**
 * 可转债外链 URL 构造测试（#1971）。
 *
 * 断言全部来自 2026-10-09 的真实探测（curl + 真机 Edge），不是从代码反推的自我印证：
 * - 集思录单券详情页 `/data/convert_bond_detail/<code>` **存在**，但游客 302 跳登录页
 *   （base64 解码回原路径，证明路由真实、非 404）；
 * - 列表页 `?bond_id=<code>` 只定位不跳转，且游客只见前 30 只；
 * - `bond_id` === 6 位债券代码；
 * - 东财转债单券页只有深市可用，沪市 302 → 404。
 *
 * **反向验证**：
 * - 把详情页 URL 换回 `cbnew/detail_<code>`（已验证只回落列表页）→ 必须转红；
 * - 让 `buildEastmoneyBondUrl` 不再拦沪市 → 必须转红。
 */
import { describe, expect, it } from "vitest";
import {
  BOND_DETAIL_LOGIN_NOTE,
  BOND_EXTERNAL_VISIBILITY_NOTE,
  buildBondExternalUrl,
  buildEastmoneyBondUrl,
  buildJisiluBondDetailUrl,
  extractBondCode,
  JISILU_CB_CENTER_URL
} from "../bondExternalLinks";

describe("extractBondCode · 债券代码提取", () => {
  it("裸 6 位代码原样返回", () => {
    expect(extractBondCode("113050")).toBe("113050");
    expect(extractBondCode("128142")).toBe("128142");
    expect(extractBondCode("127089")).toBe("127089");
  });

  it("标准化 symbol 剥掉市场前缀", () => {
    expect(extractBondCode("SH113050")).toBe("113050");
    expect(extractBondCode("SZ128142")).toBe("128142");
  });

  it("大小写与空白容错", () => {
    expect(extractBondCode("  sh113050 ")).toBe("113050");
    expect(extractBondCode("sz128142")).toBe("128142");
  });

  it("非转债代码返回 null（宁可不渲染，也不给坏链接）", () => {
    expect(extractBondCode("")).toBeNull();
    expect(extractBondCode("600519")).toBeNull(); // 股票代码，非转债
    expect(extractBondCode("000001")).toBeNull();
    expect(extractBondCode("11305")).toBeNull(); // 5 位
    expect(extractBondCode("1130500")).toBeNull(); // 7 位
    expect(extractBondCode("SH600519")).toBeNull(); // 沪市股票
  });
});

describe("buildJisiluBondDetailUrl · 集思录单券详情页（实测真实存在）", () => {
  it("命中 convert_bond_detail 路径", () => {
    expect(buildJisiluBondDetailUrl("127089")).toBe(
      "https://www.jisilu.cn/data/convert_bond_detail/127089"
    );
  });

  it("symbol 与裸代码产出同一 URL（bond_id === 6 位代码）", () => {
    const expected = "https://www.jisilu.cn/data/convert_bond_detail/113605";
    expect(buildJisiluBondDetailUrl("SH113605")).toBe(expected);
    expect(buildJisiluBondDetailUrl("113605")).toBe(expected);
  });

  it("不得回退到只回落列表页的 detail_<code> 路径", () => {
    const url = buildJisiluBondDetailUrl("113605") ?? "";
    expect(url).not.toContain("/cbnew/detail_");
    expect(url).toContain("/data/convert_bond_detail/");
  });

  it("非法代码返回 null", () => {
    expect(buildJisiluBondDetailUrl("600519")).toBeNull();
    expect(buildJisiluBondDetailUrl("")).toBeNull();
  });
});

describe("buildBondExternalUrl · 入口分流", () => {
  it("jisiluList 产出 cbnew 列表深链（游客降级入口）", () => {
    expect(buildBondExternalUrl("SH113605", "jisiluList")).toBe(
      `${JISILU_CB_CENTER_URL}?bond_id=113605`
    );
  });

  it("jisilu 入口走详情页而非列表", () => {
    const url = buildBondExternalUrl("113605", "jisilu") ?? "";
    expect(url).not.toContain("cbnew");
    expect(url).toContain("convert_bond_detail");
  });

  it("非法代码返回 null，不回退到首页", () => {
    expect(buildBondExternalUrl("600519", "jisilu")).toBeNull();
    expect(buildBondExternalUrl("", "jisiluList")).toBeNull();
  });
});

describe("buildEastmoneyBondUrl · 东财（实测仅深市可用）", () => {
  it("深市转债返回可用单券页", () => {
    expect(buildEastmoneyBondUrl("128142")).toBe(
      "https://quote.eastmoney.com/bond/sz128142.html"
    );
    expect(buildEastmoneyBondUrl("123285")).toBe(
      "https://quote.eastmoney.com/bond/sz123285.html"
    );
  });

  it("沪市转债返回 null（实测 302→q/1.<code>.html 后 404）", () => {
    expect(buildEastmoneyBondUrl("113050")).toBeNull();
    expect(buildBondExternalUrl("SH113050", "eastmoney")).toBeNull();
  });

  it("非法代码返回 null", () => {
    expect(buildEastmoneyBondUrl("600519")).toBeNull();
  });
});

describe("文案约束 · 两条实测限制都必须说明", () => {
  it("详情页登录墙必须点明（游客 302 跳登录页）", () => {
    expect(BOND_DETAIL_LOGIN_NOTE).toContain("登录");
  });

  it("游客 30 只限制必须点明，否则用户以为链接坏了", () => {
    expect(BOND_EXTERNAL_VISIBILITY_NOTE).toContain("30");
    expect(BOND_EXTERNAL_VISIBILITY_NOTE).toContain("登录");
  });
});
