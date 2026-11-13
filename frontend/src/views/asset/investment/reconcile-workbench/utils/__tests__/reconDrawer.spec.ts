/**
 * 对账抽屉三条纯判据的回归网（2026-11-12）。
 *
 * 钉住三件事：
 * 1. 头部产品标识只从 payload 取一次（orphan / import 没有「产品」可指认）；
 * 2. 投资轨迹取数键带不带 ledger_id（决定流水按账本查还是按代码查）；
 * 3. 未归属账本的流水**编辑置灰有原因**、删除不受限——判据是「哪行可编辑」
 *    的唯一真源，不许模板里临时写 `v-if`。
 */
import { describe, expect, it } from "vitest";

import type { ReconQueuePayload } from "../reconQueue";
import {
  reconItemAsset,
  reconTrailQuery,
  trailEditBlockReason
} from "../reconDrawer";

/**
 * 按 kind 造一个最小 payload（字段按需给，用不到的交给类型断言）。
 * 顶层载荷形状按 kind 分两派：danglingStage 的 stage/groups 在顶层，
 * 其余 kind 的业务字段都包在 row 里——拍平会直接打进 reconDrawer 的
 * `payload.row.symbol` 读取点，测试看似在测顶层字段、实际全踩空。
 */
function payload(
  kind: ReconQueuePayload["kind"],
  extra: object
): ReconQueuePayload {
  return kind === "danglingStage"
    ? ({ kind, ...extra } as unknown as ReconQueuePayload)
    : ({ kind, row: extra } as unknown as ReconQueuePayload);
}

/** 造一个最小悬空组（只给判据要用的字段） */
function danglingGroup(
  extra: Partial<{
    symbol: string;
    ledger_id: number;
    display_name: string | null;
  }>
): object {
  return {
    key: "g",
    ledger_id: 12,
    symbol: "SZ000725",
    display_name: null,
    txn_count: 1,
    fixable: false,
    ...extra
  };
}

describe("reconItemAsset：头部产品标识的唯一来源", () => {
  it("discrepancy：symbol + display_name，头部不再靠卡片取名字", () => {
    expect(
      reconItemAsset(
        payload("discrepancy", { symbol: "SZ000725", display_name: "京东方 A" })
      )
    ).toEqual({ symbol: "SZ000725", name: "京东方 A" });
  });

  it("display_name 缺失时给 null，不臆造名称（单组执行区）", () => {
    expect(
      reconItemAsset(
        payload("danglingStage", {
          stage: "reattach",
          groups: [danglingGroup({})]
        })
      )
    ).toEqual({ symbol: "SZ000725", name: null });
  });

  it("danglingStage 多组聚合：没有单一产品可指认，头部退回阶段标题", () => {
    expect(
      reconItemAsset(
        payload("danglingStage", {
          stage: "fill",
          groups: [danglingGroup({}), danglingGroup({ symbol: "SH600000" })]
        })
      )
    ).toBeNull();
  });

  it("tax：name 为空串时归一成 null", () => {
    expect(
      reconItemAsset(payload("tax", { symbol: "OF000001", name: "" }))
    ).toEqual({ symbol: "OF000001", name: null });
  });

  it("ghostIgnored：symbol 可为 null，此时给空串让头部退回 item.title", () => {
    expect(
      reconItemAsset(
        payload("ghostIgnored", { symbol: null, display_name: null })
      )
    ).toEqual({ symbol: "", name: null });
  });

  it("eaccount：E账户行也有产品标识", () => {
    expect(
      reconItemAsset(
        payload("eaccount", { symbol: "OF000001", name: "测试基金" })
      )
    ).toEqual({ symbol: "OF000001", name: "测试基金" });
  });

  it("orphan / import 指认的是账本或入口，没有产品可指认", () => {
    expect(
      reconItemAsset(payload("orphan", { resolved_ledger: {} }))
    ).toBeNull();
    expect(reconItemAsset(payload("import", {}))).toBeNull();
  });
});

describe("reconTrailQuery：投资轨迹的取数键", () => {
  it("discrepancy 带 ledger_id（按账本 + 代码查）；danglingStage 单组同样给键", () => {
    expect(
      reconTrailQuery(
        payload("discrepancy", { symbol: "SZ000725", ledger_id: 12 })
      )
    ).toEqual({ symbol: "SZ000725", ledgerId: 12 });
    expect(
      reconTrailQuery(
        payload("danglingStage", {
          stage: "reattach",
          groups: [danglingGroup({ symbol: "SH600000", ledger_id: 7 })]
        })
      )
    ).toEqual({ symbol: "SH600000", ledgerId: 7 });
  });

  it("danglingStage 多组聚合不开轨迹：没有单一标的可画", () => {
    expect(
      reconTrailQuery(
        payload("danglingStage", {
          stage: "rebuild",
          groups: [danglingGroup({}), danglingGroup({})]
        })
      )
    ).toBeNull();
  });

  it("tax / eaccount / ghost 无单一账本，按代码查", () => {
    for (const kind of ["tax", "eaccount", "ghost"] as const) {
      expect(reconTrailQuery(payload(kind, { symbol: "SH600000" }))).toEqual({
        symbol: "SH600000",
        ledgerId: null
      });
    }
  });

  it("orphan / import 没有产品，不开轨迹", () => {
    expect(reconTrailQuery(payload("orphan", {}))).toBeNull();
    expect(reconTrailQuery(payload("import", {}))).toBeNull();
  });
});

describe("trailEditBlockReason：未归账本的流水编辑置灰（删除不受限）", () => {
  it("已归属账本：空串 = 可编辑", () => {
    expect(trailEditBlockReason({ ledger_id: 12 })).toBe("");
  });

  it("ledger_id 为 null：给一句能看懂、且指得明去处的置灰原因", () => {
    const reason = trailEditBlockReason({ ledger_id: null });
    expect(reason).not.toBe("");
    expect(reason).toContain("账本");
    // 不能只说「不能编辑」却不给下一步：归置入口是账户管理页的「未归置数据」
    expect(reason).toContain("未归置数据");
  });

  it("ledger_id 缺失（后端老字段）：与 null 同判", () => {
    expect(trailEditBlockReason({ ledger_id: undefined })).not.toBe("");
  });

  it("判据只看归属，不看其它字段", () => {
    expect(trailEditBlockReason({ ledger_id: 0 })).toBe("");
  });
});
