/**
 * 买入表单本地存储单测（#980 拆分时新增）：会话快照 + 最近账户置顶。
 *
 * 这两块原先是 BuyForm 里的私有函数，出错的表现都是「静默」——快照没存上，
 * 下次进页面不预填；最近账户没置顶，用户要多翻一次下拉。故用内存 Storage 替身
 * （vitest 是 node 环境，没有 sessionStorage/localStorage）钉住三条：
 *
 * 1. 存储坏掉（私有模式 / 配额满 / 内容被改坏）时**不能抛**，一律静默降级；
 * 2. 「同一笔」判据只认 6 个字段，改备注不算重复；
 * 3. 最近账户置顶去重且只留 20 个。
 */
import { describe, it, expect, beforeEach } from "vitest";
import {
  buildBuySnapshot,
  isSameAsLastSubmitted,
  loadBuyLastSubmitted,
  saveBuyLastSubmitted,
  snapshotToFormPatch,
  snapshotToSecurityOption,
  type BuyLastSubmitted
} from "../buyLastSubmitted";
import {
  bumpRecentLedger,
  loadRecentLedgerIds,
  sortByRecentUsage
} from "../buyRecentLedgers";

class MemoryStorage {
  private store = new Map<string, string>();
  getItem(key: string) {
    return this.store.has(key) ? this.store.get(key)! : null;
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value));
  }
  removeItem(key: string) {
    this.store.delete(key);
  }
  clear() {
    this.store.clear();
  }
  get length() {
    return this.store.size;
  }
  key(index: number) {
    return [...this.store.keys()][index] ?? null;
  }
}

beforeEach(() => {
  (globalThis as any).sessionStorage = new MemoryStorage();
  (globalThis as any).localStorage = new MemoryStorage();
});

function mkSnapshot(
  overrides: Partial<BuyLastSubmitted> = {}
): BuyLastSubmitted {
  return {
    ledger_id: 7,
    symbol: "110011",
    name: "易方达中小盘",
    market: "CN_A",
    type: "fund",
    trade_date: "2026-10-23",
    buyAmount: 1000,
    shares: 285.2857,
    fee: 1.5,
    ...overrides
  };
}

describe("isSameAsLastSubmitted", () => {
  it("六个判据全等即视为同一笔", () => {
    expect(isSameAsLastSubmitted(mkSnapshot(), mkSnapshot())).toBe(true);
  });

  it("金额不同不是同一笔", () => {
    expect(
      isSameAsLastSubmitted(mkSnapshot(), mkSnapshot({ buyAmount: 1001 }))
    ).toBe(false);
  });

  it("手续费不同不是同一笔（费率改动会重算费用）", () => {
    expect(isSameAsLastSubmitted(mkSnapshot(), mkSnapshot({ fee: 1.6 }))).toBe(
      false
    );
  });

  it("账户或日期不同不是同一笔", () => {
    expect(
      isSameAsLastSubmitted(mkSnapshot(), mkSnapshot({ ledger_id: 8 }))
    ).toBe(false);
    expect(
      isSameAsLastSubmitted(
        mkSnapshot(),
        mkSnapshot({ trade_date: "2026-10-24" })
      )
    ).toBe(false);
  });
});

describe("会话快照读写", () => {
  it("没存过时返回 null", () => {
    expect(loadBuyLastSubmitted()).toBeNull();
  });

  it("存取往返一致", () => {
    saveBuyLastSubmitted(mkSnapshot());
    expect(loadBuyLastSubmitted()).toEqual(mkSnapshot());
  });

  it("内容被改坏时不抛错，返回 null", () => {
    sessionStorage.setItem("fm:buy:last_submitted", "{broken");
    expect(loadBuyLastSubmitted()).toBeNull();
  });

  it("既没有账户也没有代码的垃圾快照视为无效", () => {
    saveBuyLastSubmitted(mkSnapshot({ ledger_id: null, symbol: "" }));
    expect(loadBuyLastSubmitted()).toBeNull();
  });

  it("存储抛错（配额满 / 私有模式）时静默失败", () => {
    (globalThis as any).sessionStorage = {
      getItem() {
        throw new Error("quota");
      },
      setItem() {
        throw new Error("quota");
      }
    };
    expect(loadBuyLastSubmitted()).toBeNull();
    expect(() => saveBuyLastSubmitted(mkSnapshot())).not.toThrow();
  });
});

describe("快照 → 表单回填映射", () => {
  it("只回填账户与标的，金额/日期/份额/手续费一律不带", () => {
    const patch = snapshotToFormPatch(mkSnapshot());
    expect(patch).toEqual({
      ledger_id: 7,
      symbol: "110011",
      name: "易方达中小盘",
      market: "CN_A",
      type: "fund"
    });
    expect("buyAmount" in patch).toBe(false);
    expect("trade_date" in patch).toBe(false);
  });

  it("回显项按类型给中文标签", () => {
    expect(snapshotToSecurityOption(mkSnapshot()).type_label).toBe("基金");
    expect(
      snapshotToSecurityOption(mkSnapshot({ type: "stock" })).type_label
    ).toBe("股票");
  });

  it("buildBuySnapshot 只取快照字段", () => {
    const snap = buildBuySnapshot({
      ...mkSnapshot(),
      // 表单里还有 notes/allocation 等，快照不关心
      notes: "定投",
      allocation: "longterm"
    } as any);
    expect(Object.keys(snap).sort()).toEqual(
      [
        "buyAmount",
        "fee",
        "ledger_id",
        "market",
        "name",
        "shares",
        "symbol",
        "trade_date",
        "type"
      ].sort()
    );
  });
});

describe("最近账户置顶", () => {
  it("提交成功后置顶且不重复", () => {
    bumpRecentLedger(3);
    bumpRecentLedger(9);
    bumpRecentLedger(3);
    expect(loadRecentLedgerIds()).toEqual([3, 9]);
  });

  it("只保留最近 20 个", () => {
    for (let i = 1; i <= 25; i++) bumpRecentLedger(i);
    const ids = loadRecentLedgerIds();
    expect(ids).toHaveLength(20);
    expect(ids[0]).toBe(25);
  });

  it("ledgerId 为 0 时不写入", () => {
    bumpRecentLedger(0);
    expect(loadRecentLedgerIds()).toEqual([]);
  });

  it("按最近顺序置顶，其余保持原序", () => {
    const items = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }];
    expect(sortByRecentUsage(items, [3, 1])).toEqual([
      { id: 3 },
      { id: 1 },
      { id: 2 },
      { id: 4 }
    ]);
  });

  it("没有最近记录时原样返回", () => {
    const items = [{ id: 1 }, { id: 2 }];
    expect(sortByRecentUsage(items, [])).toBe(items);
  });
});
