/**
 * 阶段归属（漏斗）判据层的单测（2026-11-13）。
 *
 * spec：docs/working-notes/recon-funnel-2026-11-13.md §3.1。
 *
 * 这张网钉住三件会让漏斗重新长出第二入口的事：
 *  ① `danglingStageOf` 脱离 `danglingNextStep` 另写一份条件 → 阶段归属与
 *     动作名各算一次，卡片写着 A、点进去做 B（2026-11-13 刚修过的漂移）；
 *  ② 分桶漏阶段（比如把 rebuild 并回别处）→ 该阶段的流水在队列里消失；
 *  ③ 空组混进某个阶段 → 队列出现「没有可处理交易」的假待办。
 */
import { describe, expect, it } from "vitest";
import {
  DANGLING_ACTION_LABEL,
  DANGLING_STAGES,
  bucketByStage,
  danglingNextStep,
  danglingStageOf,
  groupStage
} from "../danglingRefEnrichScope";

describe("danglingStageOf：全部输入组合的阶段归属", () => {
  /**
   * 2（symbol 空/非空）× 2（fixable）× 2（txnCount 0/非 0）= 8 种组合全部
   * 断言，与 `danglingNextStep` 的语义一一对应。变异探针③（另写一份条件、
   * 不走 danglingNextStep）必须在这张真值表上转红——漏掉任何一格
   * （最典型是 empty → null）都会被抓。
   */
  function stageOf(
    symbol: string | null,
    fixable: boolean,
    txnCount: number
  ): string | null {
    return danglingStageOf({ symbol, fixable, txnCount });
  }

  it("与 danglingNextStep 的四种状态一一对应（empty → null）", () => {
    // 空组优先于一切：不是阶段，是「不展示」
    expect(stageOf("SZ128021", true, 0)).toBeNull();
    expect(stageOf(null, true, 0)).toBeNull();
    // 能挂回优先于缺代码：后端已判定归属，补字段没有意义
    expect(stageOf("SZ128021", true, 7)).toBe("reattach");
    expect(stageOf(null, true, 3)).toBe("reattach");
    // 缺代码 → 补全信息（补字段真的能解决）
    expect(stageOf(null, false, 7)).toBe("fill");
    expect(stageOf("", false, 7)).toBe("fill");
    expect(stageOf("   ", false, 7)).toBe("fill");
    // 代码齐、没有同标的持仓行 → 重建持仓
    expect(stageOf("SZ128021", false, 7)).toBe("rebuild");
  });

  it("确实由 danglingNextStep 派生：逐格等价于它去掉 empty", () => {
    for (const symbol of [null, "", "SZ128021"]) {
      for (const fixable of [true, false]) {
        for (const txnCount of [0, 7]) {
          const input = { symbol, fixable, txnCount };
          const step = danglingNextStep(input);
          expect(danglingStageOf(input)).toBe(step === "empty" ? null : step);
        }
      }
    }
  });
});

describe("DANGLING_STAGES：固定顺序 fill → reattach → mislink → rebuild", () => {
  it("顺序稳定且恰好四个阶段", () => {
    expect(DANGLING_STAGES).toEqual(["fill", "reattach", "mislink", "rebuild"]);
  });

  it("每个阶段都有动作名（动作名与阶段键同源，不允许缺项）", () => {
    for (const stage of DANGLING_STAGES) {
      expect(DANGLING_ACTION_LABEL[stage]).toBeTruthy();
    }
    expect(DANGLING_ACTION_LABEL.fill).toBe("补全信息");
    expect(DANGLING_ACTION_LABEL.reattach).toBe("回补关联");
    expect(DANGLING_ACTION_LABEL.mislink).toBe("改挂到正确标的");
    expect(DANGLING_ACTION_LABEL.rebuild).toBe("重建持仓");
  });
});

describe("groupStage：组级判据走同一条派生链", () => {
  it("吃后端组的最小形状（symbol / fixable / txn_count）", () => {
    expect(groupStage({ symbol: "001982", fixable: true, txn_count: 7 })).toBe(
      "reattach"
    );
    expect(groupStage({ symbol: "001982", fixable: false, txn_count: 7 })).toBe(
      "rebuild"
    );
    expect(groupStage({ symbol: "", fixable: false, txn_count: 7 })).toBe(
      "fill"
    );
  });

  it("空组返回 null：空阶段不产出（防御，后端不该给出空组）", () => {
    expect(
      groupStage({ symbol: "001982", fixable: true, txn_count: 0 })
    ).toBeNull();
  });

  /**
   * 错挂组（`mislinked`）不参与 `danglingNextStep` 派生：
   * 它的 `fixable` 含义是「有同标的持仓可改挂」，照派生规则（fixable → reattach）
   * 会被判成「回补关联」，点进去却做「改挂」—— 卡片写着 A、点进去做 B。
   */
  it("错挂组归 mislink，不因 fixable=true 被误判成 reattach", () => {
    expect(
      groupStage({
        symbol: "SZ127041",
        fixable: true,
        txn_count: 1,
        mislinked: true
      })
    ).toBe("mislink");
    expect(
      groupStage({
        symbol: "SZ127041",
        fixable: false,
        txn_count: 1,
        mislinked: true
      })
    ).toBe("mislink");
  });
});

describe("bucketByStage：分桶与顺序", () => {
  const fillA = { key: "a", symbol: "", fixable: false, txn_count: 2 };
  const fillB = { key: "b", symbol: "", fixable: false, txn_count: 3 };
  const reattachA = { key: "c", symbol: "001982", fixable: true, txn_count: 7 };
  const reattachB = { key: "d", symbol: "600519", fixable: true, txn_count: 1 };
  const rebuildA = { key: "e", symbol: "001983", fixable: false, txn_count: 4 };
  const mislinkA = {
    key: "mislink|12|SZ127041",
    symbol: "SZ127041",
    fixable: true,
    txn_count: 1,
    mislinked: true
  };

  it("四桶互斥完备：每一组恰好落进一个桶", () => {
    const buckets = bucketByStage([
      fillA,
      reattachA,
      rebuildA,
      fillB,
      reattachB,
      mislinkA
    ]);
    expect(buckets.fill).toEqual([fillA, fillB]);
    expect(buckets.reattach).toEqual([reattachA, reattachB]);
    expect(buckets.mislink).toEqual([mislinkA]);
    expect(buckets.rebuild).toEqual([rebuildA]);
  });

  it("桶内保持输入顺序，不排序", () => {
    const buckets = bucketByStage([reattachB, reattachA]);
    expect(buckets.reattach).toEqual([reattachB, reattachA]);
  });

  it("空组不落进任何桶", () => {
    const buckets = bucketByStage([
      fillA,
      { key: "empty", symbol: "001982", fixable: true, txn_count: 0 }
    ]);
    const total =
      buckets.fill.length +
      buckets.reattach.length +
      buckets.mislink.length +
      buckets.rebuild.length;
    expect(total).toBe(1);
  });

  it("空输入 → 四桶全空（调用方据此跳过空阶段，不产出队列项）", () => {
    const buckets = bucketByStage([]);
    expect(buckets).toEqual({
      fill: [],
      reattach: [],
      mislink: [],
      rebuild: []
    });
  });
});
