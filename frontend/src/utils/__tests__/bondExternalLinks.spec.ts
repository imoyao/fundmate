// frontend/src/utils/__tests__/bondExternalLinks.spec.ts
/**
 * 可转债外链 URL 构造测试（#1971）。
 *
 * 这些断言全部来自 2026-10-09 的真实探测，不是从代码反推的自我印证：
 * - 集思录 `?bond_id=<code>` 会打开列表页并把该债滚动定位到视口（`bond_id` === 6 位代码）；
 * - `detail_<code>` 与 `?bond_id=` 等价，`cb_detail/?bond_id=` 才是真 404；
 * - 东财转债单券页只有深市（`12xxxx`）实测可用，沪市 302 → 404。
 *
 * **反向验证**：把 `JISILU_CB_CENTER_URL` 改回 `.../cb_detail/`，或让
 * `buildEastmoneyBondUrl` 不再拦沪市，本文件必须转红。
 */
import { describe, expect, it } from "vitest";
import {
  BOND_EXTERNAL_VISIBILITY_NOTE,
  buildBondExternalUrl,
  buildEastmoneyBondUrl,
  extractBondCode,
  JISILU_CB_CENTER_URL
} from "../bondExternalLinks";

describe("extractBondCode · 债券代码提取", () => {
  it("裸 6 位代码原样返回", () => {
    expect(extractBondCode("113050")).toBe("113050");
    expect(extractBondCode("128142")).toBe("128142");
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

describe("buildBondExternalUrl · 集思录", () => {
  it("symbol 与裸代码产出同一深链（bond_id === 6 位代码）", () => {
    const expected = `${JISILU_CB_CENTER_URL}?bond_id=113605`;
    expect(buildBondExternalUrl("SH113605", "jisilu")).toBe(expected);
    expect(buildBondExternalUrl("113605", "jisilu")).toBe(expected);
  });

  it("深市转债同样可用", () => {
    expect(buildBondExternalUrl("SZ128142", "jisilu")).toBe(
      `${JISILU_CB_CENTER_URL}?bond_id=128142`
    );
  });

  it("不使用已验证为真 404 的 cb_detail 路径", () => {
    const url = buildBondExternalUrl("113605", "jisilu");
    expect(url).not.toContain("cb_detail");
  });

  it("非法代码返回 null，不回退到首页", () => {
    expect(buildBondExternalUrl("600519", "jisilu")).toBeNull();
    expect(buildBondExternalUrl("", "jisilu")).toBeNull();
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

describe("游客可见范围说明", () => {
  it("必须点明 30 只限制，否则用户会以为链接坏了", () => {
    expect(BOND_EXTERNAL_VISIBILITY_NOTE).toContain("30");
    expect(BOND_EXTERNAL_VISIBILITY_NOTE).toContain("登录");
  });
});
