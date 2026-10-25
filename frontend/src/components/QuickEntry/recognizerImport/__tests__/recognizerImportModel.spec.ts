import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_QUOTA,
  EMPTY_QUOTA_HINT,
  LOW_QUOTA,
  buildCandidates,
  canRecognizeOf,
  domainOf,
  fileToBase64,
  recognizeFailureOf,
  usageFeatureOf,
  usageHintOf,
  usageIconOf,
  usageStateClassOf,
  type PreviewRow
} from "../recognizerImportModel";

const txnRow = {
  symbol: "110011",
  name: "易方达中小盘",
  type: "fund",
  display_type: "基金",
  op_type: "buy",
  op_type_label: "买入",
  quantity: 100,
  price: 2.5,
  amount: 250,
  fee: 0,
  trade_date: "2026-10-01",
  import_hash: "h1",
  source: "ocr",
  is_duplicate: false,
  error: null,
  warnings: []
} as PreviewRow;

const holdingRow = {
  symbol: "000001",
  name: "平安银行",
  type: "stock",
  quantity: 1000,
  price: 12.3,
  amount: 12300,
  snapshot_date: "2026-10-01",
  account_name: "招商银行",
  ledger_id: 7,
  source: "ocr",
  import_hash: "h2"
} as unknown as PreviewRow;

describe("额度三态", () => {
  it("正常：不提示、无状态类、魔杖图标", () => {
    expect(usageHintOf(5, false)).toBe("");
    expect(usageStateClassOf(5, false)).toBe("");
    expect(usageIconOf(5, false)).toBe("ep:magic-stick");
  });

  it(`剩余 ${LOW_QUOTA} 及以内 → 紧张（含文案与铃铛图标）`, () => {
    expect(usageHintOf(LOW_QUOTA, false)).toBe("额度紧张，谨慎使用");
    expect(usageStateClassOf(LOW_QUOTA, false)).toBe("is-low");
    expect(usageIconOf(LOW_QUOTA, false)).toBe("ep:bell");
    expect(usageHintOf(LOW_QUOTA + 1, false)).toBe("");
  });

  it("用尽：occupied 优先于 remaining（后端可能返回负）", () => {
    expect(usageHintOf(5, true)).toBe("额度已用尽，请明日再试");
    expect(usageStateClassOf(0, true)).toBe("is-used-up");
    expect(usageIconOf(0, true)).toBe("ep:warning");
  });
});

describe("场景 → feature / 域", () => {
  it("交易与持仓各查各的配额", () => {
    expect(usageFeatureOf("txn_import")).toBe("txn_import");
    expect(usageFeatureOf("holding_import")).toBe("holding_import");
  });

  it("交易 → 域 C，持仓 → 域 A", () => {
    expect(domainOf("txn_import")).toBe("C");
    expect(domainOf("holding_import")).toBe("A");
  });
});

describe("canRecognizeOf", () => {
  const base = {
    remaining: 3,
    occupied: false,
    tab: "image" as const,
    hasImage: true,
    text: ""
  };

  it("额度为 0 或已用尽 → 一律不可点（与输入无关）", () => {
    expect(canRecognizeOf({ ...base, remaining: 0 })).toBe(false);
    expect(canRecognizeOf({ ...base, occupied: true })).toBe(false);
  });

  it("图片通道看有没有文件，文本通道看有没有非空文本", () => {
    expect(canRecognizeOf(base)).toBe(true);
    expect(canRecognizeOf({ ...base, hasImage: false })).toBe(false);

    const text = { ...base, tab: "text" as const, hasImage: false };
    expect(canRecognizeOf({ ...text, text: "   " })).toBe(false);
    expect(canRecognizeOf({ ...text, text: " 110011 " })).toBe(true);
  });
});

describe("buildCandidates", () => {
  it("交易场景：打上 kind=txn 并带入 ledger_id", () => {
    const rows = buildCandidates([txnRow], "txn_import", 42);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      kind: "txn",
      ledger_id: 42,
      symbol: "110011"
    });
  });

  it("交易场景未选账户：不写 ledger_id（保持后端默认账本）", () => {
    expect(buildCandidates([txnRow], "txn_import", null)).toMatchObject([
      { kind: "txn" }
    ]);
    expect(buildCandidates([txnRow], "txn_import", null)[0]).not.toHaveProperty(
      "ledger_id"
    );
  });

  it("持仓场景：kind=holding，且**不**覆盖行自带的 ledger_id", () => {
    const [row] = buildCandidates([holdingRow], "holding_import", 99);
    expect(row).toMatchObject({ kind: "holding", ledger_id: 7 });
  });

  it("候选行必须脱掉响应式代理：否则带 warnings 的交易行存草稿会抛 DataCloneError", () => {
    // 预览行存在 ref 里 ⇒ 嵌套数组被 Vue 包成 Proxy；IndexedDB 的 structured clone
    // 不接受 Proxy，直接存会抛 DataCloneError（表现为「点了确认进草稿没反应」）。
    const reactiveLike = new Proxy(
      { ...txnRow, warnings: new Proxy(["份额与金额不符"], {}) },
      {}
    );
    expect(() => structuredClone(reactiveLike)).toThrow();

    const [row] = buildCandidates(
      [reactiveLike as PreviewRow],
      "txn_import",
      1
    );
    expect(() => structuredClone(row)).not.toThrow();
    expect(row).toMatchObject({ kind: "txn", warnings: ["份额与金额不符"] });
  });

  it("不就地改原行（预览表与草稿共用同一批对象）", () => {
    const frozen = { ...txnRow };
    buildCandidates([txnRow], "txn_import", 1);
    expect(txnRow).toEqual(frozen);
  });
});

describe("recognizeFailureOf", () => {
  it("503 → error，且点明不消耗次数", () => {
    const r = recognizeFailureOf({ response: { status: 503 } });
    expect(r.level).toBe("error");
    expect(r.message).toContain("不消耗次数");
  });

  it("429 → warning，优先用后端给的文案", () => {
    const fallback = recognizeFailureOf({ response: { status: 429 } });
    expect(fallback.level).toBe("warning");
    expect(fallback.message).toContain("次数已用完");

    const custom = recognizeFailureOf({
      response: { status: 429, data: { message: "今日额度已耗尽" } }
    });
    expect(custom.message).toBe("今日额度已耗尽");
  });

  it("超时 → error（ECONNABORTED 与 message 含 timeout 两种形态）", () => {
    expect(recognizeFailureOf({ code: "ECONNABORTED" }).message).toContain(
      "识别超时"
    );
    expect(
      recognizeFailureOf({ message: "timeout of 30000ms exceeded" }).message
    ).toContain("识别超时");
  });

  it("其余：后端 message → 原生 message → 兜底", () => {
    expect(
      recognizeFailureOf({
        response: { status: 500, data: { message: "炸了" } }
      }).message
    ).toBe("炸了");
    expect(recognizeFailureOf({ message: "Network Error" }).message).toBe(
      "Network Error"
    );
    expect(recognizeFailureOf({}).message).toBe("识别失败，请重试");
  });
});

describe("fileToBase64", () => {
  it("剥掉 data URL 前缀，只留纯 base64", async () => {
    class FakeReader {
      result = "data:image/png;base64,QUJD";
      onload: (() => void) | null = null;
      onerror: ((e: unknown) => void) | null = null;
      readAsDataURL() {
        this.onload?.();
      }
    }
    vi.stubGlobal("FileReader", FakeReader);
    await expect(fileToBase64({} as File)).resolves.toBe("QUJD");
    vi.unstubAllGlobals();
  });

  it("没有逗号时整串返回（非标准 data URL 兜底）", async () => {
    class FakeReader {
      result = "QUJD";
      onload: (() => void) | null = null;
      onerror: ((e: unknown) => void) | null = null;
      readAsDataURL() {
        this.onload?.();
      }
    }
    vi.stubGlobal("FileReader", FakeReader);
    await expect(fileToBase64({} as File)).resolves.toBe("QUJD");
    vi.unstubAllGlobals();
  });

  it("读取失败 → reject", async () => {
    class FakeReader {
      result = "";
      onload: (() => void) | null = null;
      onerror: ((e: unknown) => void) | null = null;
      readAsDataURL() {
        this.onerror?.(new Error("boom"));
      }
    }
    vi.stubGlobal("FileReader", FakeReader);
    await expect(fileToBase64({} as File)).rejects.toThrow("boom");
    vi.unstubAllGlobals();
  });
});

describe("兜底常量", () => {
  it("DEFAULT_QUOTA 与 EMPTY_QUOTA_HINT 保持一致口径", () => {
    expect(DEFAULT_QUOTA).toBe(5);
    expect(EMPTY_QUOTA_HINT).toContain("额度已用完");
  });
});
