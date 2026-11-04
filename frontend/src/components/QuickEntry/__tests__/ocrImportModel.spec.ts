import { describe, expect, it } from "vitest";
import {
  buildCandidates,
  buildCreatePayload,
  summarizeImport,
  OCR_IMPORT_REASON
} from "../ocrImportModel";
import type { OcrImportItem } from "@/api/ocr";

const FUND: OcrImportItem = {
  code: "110011",
  name: "易方达中小盘",
  symbol: "110011",
  type: "fund",
  venue: "OTC"
};

const ETF: OcrImportItem = {
  code: "159915",
  name: "创业板ETF",
  symbol: "SZ159915",
  type: "etf",
  market: "SZ",
  venue: "EXCHANGE"
};

describe("buildCandidates", () => {
  it("已存在的按 symbol 命中：置灰且默认不勾", () => {
    const out = buildCandidates([FUND, ETF], new Set(["SZ159915"]));
    expect(out[0]).toMatchObject({
      code: "110011",
      exists: false,
      selected: true
    });
    expect(out[1]).toMatchObject({
      code: "159915",
      exists: true,
      selected: false
    });
  });

  it("没有 symbol 时回退用 code 命中", () => {
    const noSymbol: OcrImportItem = { code: "600519", name: "贵州茅台" };
    const out = buildCandidates([noSymbol], new Set(["600519"]));
    expect(out[0].exists).toBe(true);
  });

  it("保留后端反查的 type / market / venue（导入时不再猜类型）", () => {
    const out = buildCandidates([ETF], new Set());
    expect(out[0]).toMatchObject({
      type: "etf",
      market: "SZ",
      venue: "EXCHANGE"
    });
  });

  it("空输入返回空数组", () => {
    expect(buildCandidates([], new Set())).toEqual([]);
  });
});

describe("buildCreatePayload", () => {
  it("符号有 symbol 用 symbol，没有则回退 code", () => {
    expect(buildCreatePayload(FUND, []).symbol).toBe("110011");
    const noSymbol: OcrImportItem = { code: "600519", name: "贵州茅台" };
    expect(buildCreatePayload(noSymbol, []).symbol).toBe("600519");
  });

  it("类型缺省兜基金、渠道缺省兜场外（仅缺省时兜，有值原样透传）", () => {
    const bare: OcrImportItem = { code: "000001", name: "某基金" };
    expect(buildCreatePayload(bare, [])).toMatchObject({
      asset_type: "fund",
      venue: "OTC"
    });
    expect(buildCreatePayload(ETF, [])).toMatchObject({
      asset_type: "etf",
      venue: "EXCHANGE"
    });
  });

  it("名称快照与导入理由随请求体落库", () => {
    const payload = buildCreatePayload(FUND, []);
    expect(payload.name).toBe("易方达中小盘");
    expect(payload.add_reason).toBe(OCR_IMPORT_REASON);
  });

  it("group_ids 是拷贝：外部数组后续变动不影响已构造的请求体", () => {
    const ids = [3, 7];
    const payload = buildCreatePayload(FUND, ids);
    ids.push(9);
    expect(payload.group_ids).toEqual([3, 7]);
    expect(payload.group_ids).not.toBe(ids);
  });

  it("不传分组时空数组（等价于不带该字段，只落「全部」）", () => {
    expect(buildCreatePayload(FUND, []).group_ids).toEqual([]);
  });
});

describe("summarizeImport", () => {
  it("全成功且无跳过：不出现「跳过」字样", () => {
    expect(summarizeImport({ success: 3, skipped: 0, failed: [] })).toEqual({
      level: "success",
      message: "导入成功 3 条"
    });
  });

  it("全成功但有跳过：成功文案里补跳过数", () => {
    expect(summarizeImport({ success: 2, skipped: 1, failed: [] })).toEqual({
      level: "success",
      message: "导入成功 2 条，跳过已存在 1 条"
    });
  });

  it("有失败：升级为 error 并逐条点名失败代码", () => {
    expect(
      summarizeImport({ success: 1, skipped: 1, failed: ["159915", "600519"] })
    ).toEqual({
      level: "error",
      message:
        "导入完成：成功 1 条，跳过已存在 1 条，失败 2 条（159915、600519）"
    });
  });

  it("全失败也是 error（success=0 仍要给出完整口径）", () => {
    const out = summarizeImport({ success: 0, skipped: 0, failed: ["110011"] });
    expect(out.level).toBe("error");
    expect(out.message).toContain("成功 0 条");
    expect(out.message).toContain("110011");
  });
});
