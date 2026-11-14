/**
 * 「7 个后端域 → 一条用户待办队列」映射层的回归网（2026-11-07）。
 *
 * 钉住三件事：
 * 1. **翻译完整**：队列项的可见文本里不许出现英文枚举、ISO 带 T、复合主键、
 *    裸负号、`#12` 这类内部标识（三张截图里的问题）。
 * 2. **不新增业务判据**：`state` 只反映后端 `fixable` / `block_reason`。
 * 3. **和式不变量**（design.md:858）：分诊卡条数 = 队列项 count 之和，
 *    状态分段器计数 = 队列项按状态分组之和，不各数一遍。
 */
import { describe, expect, it } from "vitest";

import type {
  DanglingRefGroup,
  DanglingRefList,
  DiscrepancyItem,
  DividendTaxPendingItem,
  GhostDuplicateGroupItem,
  OrphanLedgerGroup,
  OrphanLedgerList
} from "@/api/reconciliation";
import {
  batchableItems,
  buildReconQueue,
  countByState,
  countByTask,
  countOpenItemsByTask,
  filterQueue,
  queueBatchOptions,
  sortQueue,
  type ReconQueueSource
} from "../reconQueue";

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
    flags: ["has_candidate", "net_mismatch"],
    fixable: true,
    block_reason: null,
    transactions: [
      {
        id: 57,
        txn_type: "buy",
        trade_date: "2025-12-12T00:00:00",
        confirm_date: null,
        symbol: "001982",
        quantity: 1.05,
        amount: 1.05,
        position_id: 25
      }
    ],
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

const TAX_ROW: DividendTaxPendingItem = {
  symbol: "600519",
  name: "贵州茅台",
  account_name: "中金公司",
  year: 2026,
  status: "待核对",
  dividend_cents: 4600,
  dividend_on: "2026-08-21",
  tax_cents: 0,
  tax_on: null,
  ratio_pct: null
};

describe("翻译完整性：队列的可见文本里没有后端存储码", () => {
  it("域 F 的复合主键 / flags / active / ISO 时间都不出现（阶段聚合项）", () => {
    const source = emptySource();
    source.dangling = {
      total: 7,
      group_count: 1,
      batch_count: 1,
      null_symbol: 0,
      null_trade_date: 0,
      fixable_count: 7,
      groups: [danglingGroup()],
      batches: []
    } satisfies DanglingRefList;

    // 漏斗（2026-11-13）：域 F 在队列里是每阶段一条聚合项，标题是阶段名，
    // 标的退到事实行；flags / 存储码 / ISO 一律不出现。
    const item = buildReconQueue(source).find(i => i.sourceDomain === "F")!;
    const visible = [item.title, item.summary, ...item.facts].join(" ");

    expect(item.id).toBe("dangling-reattach");
    expect(item.title).toBe("可挂回的流水");
    expect(visible).not.toContain("20|001982");
    expect(visible).not.toContain("has_candidate");
    expect(visible).not.toContain("net_mismatch");
    expect(visible).not.toContain("active");
    expect(visible).not.toContain("T00:00:00");
    expect(visible).not.toContain("#697");
    expect(visible).toContain("已找到现存持仓");
    expect(visible).toContain("001982");
  });

  it("域 G 的 dividend_tax / -17.5 元 / → #12 / 实现说明都不出现", () => {
    const source = emptySource();
    source.orphan = {
      total: 26,
      fixable_count: 26,
      blocked_count: 0,
      batch_count: 1,
      groups: [orphanGroup()],
      batches: []
    } satisfies OrphanLedgerList;

    const item = buildReconQueue(source).find(i => i.sourceDomain === "G")!;
    const visible = [item.title, item.summary, ...item.facts].join(" ");

    expect(visible).toContain("同花顺（银河证券）");
    expect(visible).not.toContain("dividend_tax");
    expect(visible).not.toContain("→ #12");
    expect(visible).not.toContain("按账户名精确同名唯一判定");
    expect(visible).not.toContain("-17.5 元");
    expect(item.state).toBe("ready");
  });
});

describe("状态只翻译后端判据，前端不自行推导", () => {
  it("fixable=true → 可直接处理；fixable=false → 需先补全信息", () => {
    const source = emptySource();
    source.dangling = {
      total: 9,
      group_count: 2,
      batch_count: 1,
      null_symbol: 0,
      null_trade_date: 0,
      fixable_count: 7,
      groups: [
        danglingGroup(),
        danglingGroup({
          key: "20|001983",
          symbol: "001983",
          fixable: false,
          txn_count: 2,
          block_reason: "缺标的代码，补全后才能继续",
          live_position: null
        })
      ],
      batches: []
    } satisfies DanglingRefList;

    const items = buildReconQueue(source).filter(i => i.sourceDomain === "F");
    expect(items.map(i => i.state)).toEqual(["ready", "incomplete"]);
    // 批量件数 = 可直接处理聚合项的组数（2026-11-13 恢复纳入 danglingStage）
    expect(batchableItems(items)).toHaveLength(1);
  });

  /**
   * 错挂阶段（2026-11-13）：这类流水挂着**现存**持仓、只是标的对不上，
   * 既不是悬空也不是「待重建」—— 它要单独一个阶段，否则那批数据在界面上
   * 完全不可见（既不在悬空列表里，又进不了任何既有修法）。
   */
  it("错挂组自成一个阶段：状态是「需要我判断」，不进批量，也不冒充回补/重建", () => {
    const source = emptySource();
    source.dangling = {
      total: 8,
      group_count: 2,
      batch_count: 0,
      null_symbol: 0,
      null_trade_date: 0,
      fixable_count: 1,
      groups: [
        danglingGroup({ batch_id: null }),
        danglingGroup({
          key: "mislink|12|SZ127041",
          symbol: "SZ127041",
          ledger_id: 12,
          fixable: true,
          txn_count: 1,
          batch_id: null,
          batch_label: "",
          flags: ["mislinked", "no_target"],
          mislinked: true,
          fix_mode: "rebuild",
          wrong_positions: [
            {
              id: 488,
              symbol: "SZ128033",
              quantity: 30,
              ownership_status: "active"
            }
          ]
        })
      ],
      batches: []
    } satisfies DanglingRefList;

    const items = buildReconQueue(source).filter(i => i.sourceDomain === "F");
    const mislink = items.find(i => i.id === "dangling-mislink")!;

    expect(mislink.task).toBe("repair");
    expect(mislink.state).toBe("judge");
    expect(mislink.actionLabel).toBe("改挂到正确标的");
    expect(mislink.count).toBe(1);
    expect(mislink.summary).toContain("别的标的");
    expect(mislink.facts).toContain("涉及标的 SZ127041");
    // 错挂组没有导入批次语义，不许编一条假批次（"来自多个批次的导入" 同样是假话）
    expect(mislink.facts.some(f => f.includes("批次"))).toBe(false);
    expect(mislink.batchId).toBeNull();
    // 「需要我判断」不进批量：没有任何一键批量改挂的写路径
    expect(batchableItems(items)).toHaveLength(1);
    expect(batchableItems(items)[0]!.id).toBe("dangling-reattach");
  });

  it("组级可回填但逐条有一条 blocked → 整组仍需先补全（不吞掉 blocked 行）", () => {
    const source = emptySource();
    source.orphan = {
      total: 2,
      fixable_count: 1,
      blocked_count: 1,
      batch_count: 1,
      groups: [
        orphanGroup({
          transactions: [
            ...orphanGroup().transactions,
            {
              id: 3030,
              txn_type: "bond_redeem",
              trade_date: null,
              confirm_date: null,
              symbol: null,
              asset_type: null,
              account_name: "未知账户",
              amount: 100,
              created_at: null,
              resolved_ledger_id: null,
              block_reason: "找不到唯一同名账本"
            }
          ]
        })
      ],
      batches: []
    } satisfies OrphanLedgerList;

    const item = buildReconQueue(source).find(i => i.sourceDomain === "G")!;
    expect(item.state).toBe("incomplete");
  });

  it("已忽略的重复交易归「已处理」，不计入待办数", () => {
    const source = emptySource();
    source.ghostIgnored = [
      {
        id: 1,
        fingerprint: "fp-1",
        symbol: "600519",
        confirm_date: "2026-10-20",
        txn_type: "buy",
        amount_yuan: 17000,
        ledger_names: ["主账本"],
        reason: null,
        ignored_at: null
      }
    ];
    const item = buildReconQueue(source).find(
      i => i.payload.kind === "ghostIgnored"
    )!;
    expect(item.state).toBe("done");
    expect(countByTask(buildReconQueue(source), "verify")).toBe(0);
  });
});

describe("和式不变量：卡片条数与状态计数与队列同源", () => {
  function fullSource(): ReconQueueSource {
    const source = emptySource();
    source.discrepancies = [
      {
        id: 1,
        domain: "B",
        ledger_id: 1,
        symbol: "000001",
        discrepancy_type: "quantity",
        expected_value: 100,
        actual_value: 90,
        diff: -10,
        status: "pending",
        is_permanent: false,
        first_detected_at: null,
        updated_at: null
      }
    ];
    source.taxItems = [TAX_ROW];
    source.dangling = {
      total: 7,
      group_count: 1,
      batch_count: 1,
      null_symbol: 0,
      null_trade_date: 0,
      fixable_count: 7,
      groups: [danglingGroup()],
      batches: []
    } satisfies DanglingRefList;
    source.orphan = {
      total: 26,
      fixable_count: 26,
      blocked_count: 0,
      batch_count: 1,
      groups: [orphanGroup()],
      batches: []
    } satisfies OrphanLedgerList;
    return source;
  }

  it("修正数据的卡上条数 = 7 + 26，不把分组数当记录数", () => {
    const items = buildReconQueue(fullSource());
    expect(countByTask(items, "repair")).toBe(33);
    expect(items.filter(i => i.task === "repair")).toHaveLength(2);
  });

  it("分诊卡角标数「几件事」而不是「几条记录」，入口动作不算待办", () => {
    const items = buildReconQueue(fullSource());
    expect(countByTask(items, "repair")).toBe(33); // 33 条流水
    expect(countOpenItemsByTask(items, "repair")).toBe(2); // 2 组待办
    // 导入入口是动作而非记录（count=0），不该给「补记缺漏」挂一个假的待办角标
    expect(countOpenItemsByTask(items, "supplement")).toBe(1); // 只有那笔分红税
  });

  it("状态分段器计数 = 队列按状态分组的项数", () => {
    const items = buildReconQueue(fullSource());
    const counts = countByState(items, "all");
    const sum = Object.values(counts).reduce((a, b) => a + b, 0);
    expect(sum).toBe(items.length);
    expect(counts.ready).toBe(2);
    expect(counts.judge).toBe(3); // 差异 B + 分红税 + 导入入口
  });

  it("筛选四个维度同时生效，互不覆盖", () => {
    const items = buildReconQueue(fullSource());
    expect(
      filterQueue(items, {
        task: "repair",
        state: "ready",
        keyword: "001982",
        batchId: 1
      })
    ).toHaveLength(1);
    expect(
      filterQueue(items, {
        task: "repair",
        state: "ready",
        keyword: "不存在的标的",
        batchId: 1
      })
    ).toHaveLength(0);
  });

  it("默认排序把「可直接处理」排在最前", () => {
    const items = sortQueue(buildReconQueue(fullSource()));
    expect(items[0].state).toBe("ready");
  });

  it("批次选项只列真实批次且去重", () => {
    const options = queueBatchOptions(buildReconQueue(fullSource()));
    expect(options.map(o => o.id)).toEqual([1, 2]);
    expect(options[0].label).toContain("来自 2026-06-07 18:33 的导入");
  });
});

/* ── 第三轮：D/F/G 统一口径「标题=名称、代码作次要事实行」 ─────────────── */
describe("D/F/G 条目标题取 display_name，代码降级为事实行", () => {
  function ghostGroup(
    over: Partial<GhostDuplicateGroupItem> = {}
  ): GhostDuplicateGroupItem {
    return {
      fingerprint: "fp-ghost",
      symbol: "SH515250",
      symbol_identity: "515250",
      confirm_date: "2026-10-20",
      txn_type: "buy",
      amount_yuan: 17000,
      ledger_ids: [1, 2],
      ledger_names: ["主账本", "备用账本"],
      count: 2,
      transactions: [],
      ...over
    };
  }

  it("域 D：display_name 存在时标题是名称，事实行含「代码 X」", () => {
    const items = buildReconQueue({
      ...emptySource(),
      ghostGroups: [ghostGroup({ display_name: "中证 500ETF 联接" })]
    });
    const row = items.find(i => i.payload.kind === "ghost")!;
    expect(row.title).toBe("中证 500ETF 联接");
    expect(row.facts.join(" ")).toContain("代码 SH515250");
  });

  it("域 D：display_name 为 null 时标题回落代码", () => {
    const items = buildReconQueue({
      ...emptySource(),
      ghostGroups: [ghostGroup({ display_name: null })]
    });
    const row = items.find(i => i.payload.kind === "ghost")!;
    expect(row.title).toBe("SH515250");
    expect(row.facts.join(" ")).toContain("代码 SH515250");
  });

  it("域 D 已忽略条目同样走名称口径，不再裸插值 symbol", () => {
    const items = buildReconQueue({
      ...emptySource(),
      ghostIgnored: [
        {
          id: 1,
          fingerprint: "fp-1",
          symbol: "SH515250",
          display_name: "中证 500ETF 联接",
          confirm_date: "2026-10-20",
          txn_type: "buy",
          amount_yuan: 17000,
          ledger_names: ["主账本"],
          reason: null,
          ignored_at: null
        }
      ]
    });
    const row = items.find(i => i.payload.kind === "ghostIgnored")!;
    expect(row.title).toBe("中证 500ETF 联接");
    expect(row.facts.join(" ")).toContain("代码 SH515250");
  });

  it("域 D 已忽略条目 symbol 快照为 null 时标题给可执行提示而非空白", () => {
    const items = buildReconQueue({
      ...emptySource(),
      ghostIgnored: [
        {
          id: 1,
          fingerprint: "fp-1",
          symbol: null,
          display_name: null,
          confirm_date: null,
          txn_type: null,
          amount_yuan: null,
          ledger_names: [],
          reason: null,
          ignored_at: null
        }
      ]
    });
    const row = items.find(i => i.payload.kind === "ghostIgnored")!;
    expect(row.title).toBe("标的代码未填");
  });

  it("域 F：display_name 存在时名称进事实行，标题让位阶段名（漏斗聚合）", () => {
    const source = emptySource();
    source.dangling = {
      total: 7,
      group_count: 1,
      batch_count: 1,
      null_symbol: 0,
      null_trade_date: 0,
      fixable_count: 7,
      groups: [danglingGroup({ display_name: "华安创业板 50" })],
      batches: []
    } satisfies DanglingRefList;
    const row = buildReconQueue(source).find(i => i.sourceDomain === "F")!;
    // 聚合项代表一个阶段而不是一组流水，标题不再点名标的；名称进事实行
    expect(row.title).toBe("可挂回的流水");
    expect(row.facts.join(" ")).toContain("华安创业板 50");
  });

  it("域 F：display_name 为 null 时事实行退回代码，不臆造名称", () => {
    const source = emptySource();
    source.dangling = {
      total: 7,
      group_count: 1,
      batch_count: 1,
      null_symbol: 0,
      null_trade_date: 0,
      fixable_count: 7,
      groups: [danglingGroup({ display_name: null })],
      batches: []
    } satisfies DanglingRefList;
    const row = buildReconQueue(source).find(i => i.sourceDomain === "F")!;
    expect(row.title).toBe("可挂回的流水");
    expect(row.facts.join(" ")).toContain("001982");
  });
});

/* ── 第二轮：产品名 / cash / 差异术语（owner 截图反馈） ───────────────── */
describe("队列里不再出现「只有代码」「裸 cash」「孤儿」", () => {
  function disc(over: Partial<DiscrepancyItem> = {}): DiscrepancyItem {
    return {
      id: 1,
      domain: "B",
      ledger_id: 20,
      symbol: "SH688223",
      discrepancy_type: "quantity",
      expected_value: 100,
      actual_value: 140,
      diff: 40,
      status: "pending",
      is_permanent: false,
      first_detected_at: null,
      updated_at: null,
      ...over
    };
  }

  function visibleText(items: ReturnType<typeof buildReconQueue>): string {
    return items
      .map(i => `${i.title} ${i.summary} ${i.facts.join(" ")}`)
      .join(" ");
  }

  it("后端给了 display_name 时标题用名称，代码仍留在事实行", () => {
    const items = buildReconQueue({
      ...emptySource(),
      discrepancies: [disc({ display_name: "××科创板基金" })]
    });
    const row = items.find(i => i.id === "disc-1");
    expect(row?.title).toBe("××科创板基金");
    expect(row?.facts.join(" ")).toContain("SH688223");
    expect(row?.summary).toContain("份额对不上");
  });

  it("没有名称时退到代码，不臆造产品名", () => {
    const items = buildReconQueue({
      ...emptySource(),
      discrepancies: [disc()]
    });
    expect(items.find(i => i.id === "disc-1")?.title).toBe("SH688223");
  });

  it("差异数字改用「按流水算 / 账上记的 / 差多少」，不再说理论实际", () => {
    const row = buildReconQueue({
      ...emptySource(),
      discrepancies: [disc()]
    }).find(i => i.id === "disc-1");
    const facts = row?.facts.join(" ") ?? "";
    expect(facts).toContain("按流水算");
    expect(facts).toContain("账上记的");
    expect(facts).toContain("差多少");
    expect(facts).not.toContain("理论");
    expect(facts).not.toContain("实际");
  });

  it("orphan 说人话，界面零「孤儿」", () => {
    const items = buildReconQueue({
      ...emptySource(),
      discrepancies: [disc({ domain: "C", discrepancy_type: "orphan" })]
    });
    expect(visibleText(items)).not.toContain("孤儿");
    expect(visibleText(items)).toContain("有持仓");
  });

  it("cash 分红显示成「现金」，可见文本零裸 cash", () => {
    const cashTax: DividendTaxPendingItem = {
      symbol: "cash",
      name: "",
      account_name: "测试账户",
      year: 2026,
      status: "待核对",
      dividend_cents: 50000,
      dividend_on: "2026-06-20",
      tax_cents: 0,
      tax_on: null,
      ratio_pct: null
    };
    const items = buildReconQueue({ ...emptySource(), taxItems: [cashTax] });
    expect(visibleText(items)).toContain("现金");
    expect(visibleText(items)).not.toContain("cash");
    expect(visibleText(items)).toContain("不是一只产品");
  });
});

/**
 * 一个数据只有一个唯一入口（2026-11-14，owner 截图）。
 *
 * 被域 F 悬空组覆盖的 orphan 差异，唯一能修的地方是「修正数据 → 按流水重建持仓」；
 * 核对差异里那行点进去补录，最后一步会被后端拦下（持仓行不存在）并把人指回修正数据。
 * 所以它不进队列。**没被覆盖的 orphan 要留下**——真库 8 条持仓行还在（份额已清零），
 * 一刀切剔除等于把真差异藏起来。
 */
describe("入口唯一：域 F 覆盖的孤儿差异不进核对差异", () => {
  function orphanRow(over: Partial<DiscrepancyItem> = {}): DiscrepancyItem {
    return {
      id: 9,
      domain: "B",
      ledger_id: 20,
      symbol: "001982",
      discrepancy_type: "orphan",
      expected_value: 71.68,
      actual_value: 0,
      diff: -71.68,
      status: "pending",
      is_permanent: false,
      first_detected_at: null,
      updated_at: null,
      ...over
    };
  }

  function sourceWithOrphan(
    rows: DiscrepancyItem[],
    groups: DanglingRefGroup[]
  ): ReconQueueSource {
    return {
      ...emptySource(),
      discrepancies: rows,
      dangling: {
        total: groups.reduce((sum, g) => sum + g.txn_count, 0),
        group_count: groups.length,
        batch_count: 0,
        null_symbol: 0,
        null_trade_date: 0,
        fixable_count: 0,
        groups,
        batches: []
      }
    };
  }

  it("同键悬空组在 → 该 orphan 差异不出现在队列里", () => {
    const items = buildReconQueue(
      sourceWithOrphan([orphanRow()], [danglingGroup()])
    );
    expect(items.find(i => i.id === "disc-9")).toBeUndefined();
    // 域 F 自己的阶段项仍在（入口移到那里，不是丢掉）
    expect(items.some(i => i.sourceDomain === "F")).toBe(true);
  });

  it("域 F 没覆盖（持仓行还在、份额已清零）→ 仍留在队列里", () => {
    const items = buildReconQueue(
      sourceWithOrphan(
        [orphanRow({ symbol: "SH600103" })],
        [danglingGroup({ symbol: "001982", key: "20|001982" })]
      )
    );
    expect(items.find(i => i.id === "disc-9")?.title).toBe("SH600103");
  });

  it("同键的 quantity 差异不受影响：它的修法本来就在核对差异里", () => {
    const items = buildReconQueue(
      sourceWithOrphan(
        [orphanRow({ discrepancy_type: "quantity", diff: -40 })],
        [danglingGroup()]
      )
    );
    expect(items.find(i => i.id === "disc-9")).toBeDefined();
  });

  it("域 F 数据没加载成功（null）时不剔除任何差异：宁多显示，不静默隐藏", () => {
    const items = buildReconQueue({
      ...emptySource(),
      discrepancies: [orphanRow()]
    });
    expect(items.find(i => i.id === "disc-9")).toBeDefined();
  });
});

/**
 * 2026-11-13：不可回补组有两种成因，动作名必须分开。
 *
 * 代码齐全、只缺持仓行的组，点「补全信息」进去是一张「没有可补的字段」的死弹窗，
 * 而弹窗又把用户指回列表去「补建持仓」——两边来回踢皮球（owner 截图）。
 * 判据收在 `danglingNextStep`，队列卡的动作名必须与它一致。
 */
describe("域 F 的下一步动作与判据同源", () => {
  function danglingSource(group: DanglingRefGroup): ReconQueueSource {
    return {
      ...emptySource(),
      dangling: {
        total: group.txn_count,
        group_count: 1,
        batch_count: 1,
        null_symbol: 0,
        null_trade_date: 0,
        fixable_count: group.fixable ? group.txn_count : 0,
        groups: [group],
        batches: []
      } satisfies DanglingRefList
    };
  }

  it("代码齐、没有同标的持仓行 → 动作是「重建持仓」，不是「补全信息」", () => {
    const item = buildReconQueue(
      danglingSource(
        danglingGroup({
          fixable: false,
          live_position: null,
          block_reason:
            "同账本没有同标的的现存持仓行，无法挂回；可按流水重建持仓"
        })
      )
    ).find(i => i.sourceDomain === "F")!;

    expect(item.id).toBe("dangling-rebuild");
    // rebuild 自成任务（待重建持仓），不再挂在「修正数据」下
    expect(item.task).toBe("rebuild");
    expect(item.actionLabel).toBe("重建持仓");
    expect(item.state).toBe("incomplete");
    // 原因要说清「缺的是持仓行」，不是「缺字段」——后者会让人去填一张没有字段的表单
    expect(item.stateReason).toBe("流水完整，缺的是它对应的持仓行");
  });

  it("缺标的代码 → 动作仍是「补全信息」（补字段真的能解决）", () => {
    const item = buildReconQueue(
      danglingSource(
        danglingGroup({
          symbol: "",
          fixable: false,
          live_position: null,
          block_reason: "这批流水缺标的代码，无法判定归属"
        })
      )
    ).find(i => i.sourceDomain === "F")!;

    expect(item.id).toBe("dangling-fill");
    expect(item.task).toBe("repair");
    expect(item.actionLabel).toBe("补全信息");
    expect(item.stateReason).toBe("缺标的代码，补齐后才能判断归属");
  });

  it("已找到现存持仓 → 动作是「回补关联」", () => {
    const item = buildReconQueue(danglingSource(danglingGroup())).find(
      i => i.sourceDomain === "F"
    )!;

    expect(item.id).toBe("dangling-reattach");
    expect(item.task).toBe("repair");
    expect(item.actionLabel).toBe("回补关联");
    expect(item.state).toBe("ready");
  });
});

/**
 * 阶段聚合（漏斗，2026-11-13）：队列里域 F 是「每阶段一条」，不是逐组一条。
 * 钉住四件事：每阶段最多一条、count 等于各组 txn_count 之和、空阶段不产出、
 * 和式不变量（design.md:858）跨四张分诊卡仍成立。
 */
describe("域 F 按阶段聚合：每阶段一条、条数求和、空阶段不产出", () => {
  function danglingSource(groups: DanglingRefGroup[]): ReconQueueSource {
    return {
      ...emptySource(),
      dangling: {
        total: groups.reduce((sum, g) => sum + g.txn_count, 0),
        group_count: groups.length,
        batch_count: 1,
        null_symbol: 0,
        null_trade_date: 0,
        fixable_count: groups
          .filter(g => g.fixable)
          .reduce((sum, g) => sum + g.txn_count, 0),
        groups,
        batches: []
      } satisfies DanglingRefList
    };
  }

  it("三个阶段各只有一条聚合项，id 为 dangling-<stage>", () => {
    const items = buildReconQueue(
      danglingSource([
        danglingGroup(), // reattach
        danglingGroup({
          key: "20|001983",
          symbol: "001983",
          fixable: false,
          live_position: null,
          txn_count: 4,
          transactions: []
        }), // rebuild
        danglingGroup({
          key: "20|",
          symbol: "",
          fixable: false,
          live_position: null,
          txn_count: 3,
          transactions: []
        }) // fill
      ])
    ).filter(i => i.sourceDomain === "F");

    expect(items.map(i => i.id)).toEqual([
      "dangling-fill",
      "dangling-reattach",
      "dangling-rebuild"
    ]);
  });

  it("count = 该阶段各组 txn_count 之和，payload 带阶段与组清单", () => {
    const items = buildReconQueue(
      danglingSource([
        danglingGroup(), // reattach：7
        danglingGroup({ key: "20|600519", symbol: "600519", txn_count: 2 }), // reattach：2
        danglingGroup({
          key: "20|001983",
          symbol: "001983",
          fixable: false,
          live_position: null,
          txn_count: 4,
          transactions: []
        }) // rebuild：4
      ])
    );
    const reattach = items.find(i => i.id === "dangling-reattach")!;
    const rebuild = items.find(i => i.id === "dangling-rebuild")!;

    expect(reattach.count).toBe(9); // 7 + 2
    expect(reattach.payload).toEqual({
      kind: "danglingStage",
      stage: "reattach",
      groups: expect.any(Array)
    });
    if (reattach.payload.kind === "danglingStage") {
      expect(reattach.payload.groups).toHaveLength(2);
    }
    expect(rebuild.count).toBe(4);
  });

  it("某阶段没有组 → 队列里没有它的项（空阶段不渲染）", () => {
    const items = buildReconQueue(
      danglingSource([danglingGroup()]) // 只有 reattach
    ).filter(i => i.sourceDomain === "F");
    expect(items.map(i => i.id)).toEqual(["dangling-reattach"]);
  });

  it("空清单 → 域 F 一条项都不产出", () => {
    const items = buildReconQueue(danglingSource([])).filter(
      i => i.sourceDomain === "F"
    );
    expect(items).toHaveLength(0);
  });

  it("和式不变量：四张分诊卡 count 之和 = 全部队列项 count 之和", () => {
    const source = danglingSource([
      danglingGroup(), // reattach 7
      danglingGroup({
        key: "20|001983",
        symbol: "001983",
        fixable: false,
        live_position: null,
        txn_count: 4,
        transactions: []
      }) // rebuild 4
    ]);
    source.orphan = {
      total: 26,
      fixable_count: 26,
      blocked_count: 0,
      batch_count: 1,
      groups: [orphanGroup()],
      batches: []
    } satisfies OrphanLedgerList;
    source.taxItems = [TAX_ROW];

    const items = buildReconQueue(source);
    const taskSum = (["verify", "supplement", "repair", "rebuild"] as const)
      .map(task => countByTask(items, task))
      .reduce((a, b) => a + b, 0);
    const queueSum = items
      .filter(i => i.state !== "done")
      .reduce((sum, i) => sum + i.count, 0);
    expect(taskSum).toBe(queueSum);
    // 聚合前后域 F 的记录条数不变：reattach 7 归 repair，rebuild 4 归 rebuild
    expect(countByTask(items, "repair")).toBe(7 + 26);
    expect(countByTask(items, "rebuild")).toBe(4);
  });

  it("阶段内批次一致才带批次筛选；跨批次聚合不带（否则筛掉一部分组）", () => {
    const items = buildReconQueue(
      danglingSource([
        danglingGroup({ batch_id: 1 }), // 同批次 → 带 batchId
        danglingGroup({ key: "20|600519", symbol: "600519", batch_id: 3 })
      ])
    );
    const reattach = items.find(i => i.id === "dangling-reattach")!;
    expect(reattach.batchId).toBeNull();
  });

  it("reattach 聚合项进批量集合，批量件数 = 组数（2026-11-13 恢复纳入）", () => {
    const items = buildReconQueue(
      danglingSource([
        danglingGroup(), // reattach：7
        danglingGroup({ key: "20|600519", symbol: "600519", txn_count: 2 }) // reattach：2
      ])
    );
    const batchable = batchableItems(items);
    // 唯一的 reattach 聚合项可勾选；弹窗拍平 groups 后批量件数 = 组数 2
    expect(batchable.map(i => i.id)).toEqual(["dangling-reattach"]);
    const groups = batchable[0].payload;
    if (groups.kind !== "danglingStage") throw new Error("kind 漂移");
    expect(groups.groups).toHaveLength(2);
  });
});

describe("畸形 200 响应不能把整页冻在加载态", () => {
  it("清单字段被写成汇总对象时按空数组降级，不抛错", () => {
    // e2e 实测：/ghost-duplicates/ignored/ 打错桩，宽桩返回 {groups, ignored_count}
    // 被当成数组写进 ghostIgnored → buildReconQueue 的 for...of 抛错 → Vue 只报
    // warn 并把 DOM 冻在「正在检查账上记录…」。这里钉住映射层必须自保。
    const malformed = {
      ...emptySource(),
      ghostIgnored: { groups: [], ignored_count: 0 },
      taxItems: { items: [] }
    } as unknown as ReconQueueSource;

    expect(() => buildReconQueue(malformed)).not.toThrow();
    const items = buildReconQueue(malformed);
    expect(items.map(i => i.id)).toEqual(["import-entry"]);
  });
});
