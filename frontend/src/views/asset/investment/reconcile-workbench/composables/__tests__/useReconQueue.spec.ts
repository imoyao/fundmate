/**
 * 待办队列页面状态的回归网（2026-11-19 场景化）。
 *
 * 钉三件事：
 * 1. `?domain=` 入站只重置任务维度，分段维度仍是默认「能一键处理」；
 * 2. ready=0 且 judge>0 时自动落档到「要你判断」，且首屏加载态不误落档；
 * 3. 一键处理范围 = 全量 ready 项（batchableItems），不再有勾选子集。
 */
import { describe, expect, it } from "vitest";
import { nextTick, ref } from "vue";

import type {
  DanglingRefGroup,
  DanglingRefList,
  OrphanLedgerGroup,
  OrphanLedgerList
} from "@/api/reconciliation";
import { useReconQueue } from "../useReconQueue";
import type { ReconQueueSource } from "../../utils/reconQueue";

function emptySource(): ReconQueueSource {
  return {
    discrepancies: [],
    eItems: [],
    ghostGroups: [],
    ghostIgnored: [],
    taxItems: [],
    dangling: null,
    orphan: null
  };
}

function danglingGroup(over: Partial<DanglingRefGroup> = {}): DanglingRefGroup {
  return {
    key: "20|001982",
    ledger_id: 20,
    symbol: "001982",
    txn_count: 7,
    dangling_position_ids: [25],
    net_units: 71.68,
    live_position: {
      id: 697,
      symbol: "001982",
      quantity: 96.41,
      ownership_status: "active"
    },
    candidates: [],
    batch_id: 1,
    batch_label: "2026-06-07 18:33",
    flags: [],
    fixable: true,
    block_reason: null,
    transactions: [],
    ...over
  };
}

function orphanGroup(over: Partial<OrphanLedgerGroup> = {}): OrphanLedgerGroup {
  return {
    key: "ledger:12",
    resolved_ledger: { id: 12, name: "同花顺（银河证券）" },
    txn_count: 26,
    block_reason: null,
    batch_id: 2,
    batch_label: "2026-11-02 14:24",
    transactions: [
      {
        id: 3029,
        txn_type: "dividend_tax",
        trade_date: null,
        confirm_date: null,
        symbol: null,
        asset_type: null,
        account_name: "同花顺（银河证券）",
        amount: -17.5,
        created_at: null,
        resolved_ledger_id: 12,
        block_reason: null
      }
    ],
    ...over
  };
}

describe("focusDomain：?domain= 入站的筛选口径", () => {
  it("?domain=F 不设任务筛选，分段保持默认「能一键处理」", () => {
    const source = ref<ReconQueueSource>({
      ...emptySource(),
      dangling: {
        total: 11,
        group_count: 2,
        batch_count: 1,
        null_symbol: 3,
        null_trade_date: 0,
        fixable_count: 7,
        groups: [
          danglingGroup(), // reattach → ready
          danglingGroup({
            key: "20|001983",
            symbol: "001983",
            fixable: false,
            live_position: null,
            txn_count: 4,
            transactions: []
          }) // rebuild → judge
        ],
        batches: []
      } satisfies DanglingRefList
    });
    const queue = useReconQueue(source, ref(false));

    const matchId = queue.focusDomain("F");

    expect(queue.filter.value.task).toBe("all");
    expect(queue.filter.value.segment).toBe("ready");
    expect(matchId).toBe("dangling-reattach");
    // ready 段可见 reattach；rebuild 已折入 repair，落在 judge 段
    const visibleIds = queue.visibleItems.value.map(i => i.id);
    expect(visibleIds).toContain("dangling-reattach");
    expect(queue.items.value.find(i => i.id === "dangling-rebuild")?.task).toBe(
      "repair"
    );
  });

  it("?domain=G 仍按 DOMAIN_TO_TASK 落到 repair（其余域不受影响）", () => {
    const source = ref<ReconQueueSource>({
      ...emptySource(),
      orphan: {
        total: 26,
        fixable_count: 26,
        blocked_count: 0,
        batch_count: 1,
        groups: [orphanGroup()],
        batches: []
      } satisfies OrphanLedgerList
    });
    const queue = useReconQueue(source, ref(false));

    const matchId = queue.focusDomain("G");

    expect(queue.filter.value.task).toBe("repair");
    expect(matchId).toBe("orphan-ledger:12");
  });
});

describe("ready → judge 自动落档", () => {
  it("ready=0 且 judge>0 时从 ready 落到 judge", async () => {
    const source = ref<ReconQueueSource>({
      ...emptySource(),
      dangling: {
        total: 4,
        group_count: 1,
        batch_count: 1,
        null_symbol: 0,
        null_trade_date: 0,
        fixable_count: 0,
        groups: [
          danglingGroup({
            key: "20|001983",
            symbol: "001983",
            fixable: false,
            live_position: null,
            txn_count: 4,
            transactions: []
          }) // rebuild → judge
        ],
        batches: []
      } satisfies DanglingRefList
    });
    const queue = useReconQueue(source, ref(false));

    await nextTick();

    expect(queue.filter.value.segment).toBe("judge");
  });

  it("加载态 ready=0 不落档，等数据回来再判定", async () => {
    const loading = ref(true);
    const source = ref<ReconQueueSource>(emptySource());
    const queue = useReconQueue(source, loading);

    expect(queue.filter.value.segment).toBe("ready");

    loading.value = false;
    await nextTick();
    // 全空：既没有 ready 也没有 judge，不落 judge（交给全清空态）
    expect(queue.filter.value.segment).toBe("ready");
  });
});

describe("一键处理范围 = 全量 ready 项", () => {
  it("allReadyItems 只收 ready 的 orphan / danglingStage，不收勾选子集", () => {
    const source = ref<ReconQueueSource>({
      ...emptySource(),
      dangling: {
        total: 7,
        group_count: 1,
        batch_count: 1,
        null_symbol: 0,
        null_trade_date: 0,
        fixable_count: 7,
        groups: [danglingGroup()],
        batches: []
      } satisfies DanglingRefList,
      orphan: {
        total: 26,
        fixable_count: 26,
        blocked_count: 0,
        batch_count: 1,
        groups: [orphanGroup()],
        batches: []
      } satisfies OrphanLedgerList
    });
    const queue = useReconQueue(source, ref(false));

    expect(queue.readyCount.value).toBe(2);
    expect(queue.allReadyItems.value.map(i => i.id)).toEqual([
      "dangling-reattach",
      "orphan-ledger:12"
    ]);
  });
});
