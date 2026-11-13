/**
 * 待办队列页面状态的回归网（2026-11-13）。
 *
 * 钉两件事：
 * 1. `?domain=F` 入站**不设任务筛选**：域 F 的阶段聚合项跨 repair /
 *    rebuild 两个任务，若按 DOMAIN_TO_TASK 只筛 repair，rebuild 阶段的
 *    聚合项会被整个滤掉，用户从外链进来直接看不到那张卡；
 * 2. 其余域维持 `DOMAIN_TO_TASK` 的映射行为（回归保护，防放宽成全域）。
 */
import { describe, expect, it } from "vitest";
import { ref } from "vue";

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
    transactions: [],
    ...over
  };
}

describe("focusDomain：?domain= 入站的筛选口径", () => {
  it("?domain=F 不设任务筛选：repair 与 rebuild 阶段的聚合项都可见", () => {
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
          danglingGroup(), // reattach → repair
          danglingGroup({
            key: "20|001983",
            symbol: "001983",
            fixable: false,
            live_position: null,
            txn_count: 4,
            transactions: []
          }) // rebuild → rebuild
        ],
        batches: []
      } satisfies DanglingRefList
    });
    const queue = useReconQueue(source);

    const matchId = queue.focusDomain("F");

    expect(queue.filter.value.task).toBe("all");
    expect(queue.filter.value.state).toBe("all");
    // 定位到该域排序后的第一条（ready 最靠前）
    expect(matchId).toBe("dangling-reattach");
    // 两个阶段的聚合项都在可见列表里，缺一不可
    const visibleIds = queue.visibleItems.value.map(i => i.id);
    expect(visibleIds).toContain("dangling-reattach");
    expect(visibleIds).toContain("dangling-rebuild");
  });

  it("?domain=G 仍按 DOMAIN_TO_TASK 落到 repair（其余域不受放宽影响）", () => {
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
    const queue = useReconQueue(source);

    const matchId = queue.focusDomain("G");

    expect(queue.filter.value.task).toBe("repair");
    expect(matchId).toBe("orphan-ledger:12");
  });
});
