/**
 * 无归属组「这一组能做什么」的判据单测（2026-11-19）。
 *
 * 这张网钉住两件事：
 *  ① 每一格输入都必须有出口——有主动作就给按钮文字，没有主动作就必须给原因
 *     （死胡同弹窗的根因不是文案，是「既没按钮也没话说」）；
 *  ② 净额门槛与后端同一口径（最小单位），不能用 `> 0` 让 float 尾数左右结论。
 */
import { describe, expect, it } from "vitest";
import {
  decideDanglingAction,
  inspectGroupNeeds,
  unownedOutcome,
  type UnownedOutcome
} from "../danglingRefEnrichScope";

const OUTCOMES: readonly UnownedOutcome[] = [
  "fill",
  "rebuild",
  "wait",
  "deleteOnly",
  "empty"
];

function needsOf(
  txns: { symbol?: string | null; trade_date?: string | null }[]
) {
  return inspectGroupNeeds(txns);
}

/** 字段齐全的一组（组内代码 / 日期都有） */
const completeNeeds = () =>
  needsOf([{ symbol: "118001", trade_date: "2026-04-16" }]);

describe("unownedOutcome：四种出口各就各位", () => {
  it("缺标的代码 / 缺日期 → 补全信息，原因写明缺多少条", () => {
    const noSymbol = unownedOutcome({
      needs: needsOf([
        { symbol: "", trade_date: "2026-04-16" },
        { symbol: null, trade_date: "2026-04-16" }
      ]),
      netUnits: 100,
      flags: ["no_symbol", "no_candidate"]
    });
    expect(noSymbol.outcome).toBe("fill");
    expect(noSymbol.actionLabel).toBe("补全信息");
    expect(noSymbol.reason).toContain("2 条缺标的代码");

    const noDate = unownedOutcome({
      needs: needsOf([{ symbol: "SZ160723", trade_date: null }]),
      netUnits: 100,
      flags: ["no_candidate"]
    });
    expect(noDate.outcome).toBe("fill");
    expect(noDate.reason).toContain("1 条缺交易日期");
  });

  it("字段齐 + 同账本唯一候选 → 等夜间回填（不给点不动的按钮）", () => {
    const d = unownedOutcome({
      needs: completeNeeds(),
      netUnits: 500,
      flags: ["auto_attach_after_enrich"]
    });
    expect(d.outcome).toBe("wait");
    expect(d.actionLabel).toBeNull();
    expect(d.reason).toContain("夜间回填");
  });

  it("字段齐 + 无候选 + 净额为正 → 按流水重建持仓", () => {
    const d = unownedOutcome({
      needs: completeNeeds(),
      netUnits: 2436,
      flags: ["no_candidate"]
    });
    expect(d.outcome).toBe("rebuild");
    expect(d.actionLabel).toBe("按流水重建持仓");
    expect(d.reason).toContain("净额为正");
  });

  it("字段齐 + 无候选 + 净额 ≤ 0 → 只能删除，原因说清买卖已对冲", () => {
    for (const netUnits of [-2436, 0]) {
      const d = unownedOutcome({
        needs: completeNeeds(),
        netUnits,
        flags: ["no_candidate"]
      });
      expect(d.outcome).toBe("deleteOnly");
      expect(d.actionLabel).toBeNull();
      expect(d.reason).toContain("净额 ≤ 0");
    }
  });

  it("字段齐 + 多条同标的持仓（无 flag）→ 只能删除，系统不替你选", () => {
    const d = unownedOutcome({
      needs: completeNeeds(),
      netUnits: 100,
      flags: []
    });
    expect(d.outcome).toBe("deleteOnly");
    expect(d.actionLabel).toBeNull();
    expect(d.reason).toContain("不会替你选");
  });

  it("空组 → empty，防御用（后端不该给出空组）", () => {
    const d = unownedOutcome({
      needs: needsOf([]),
      netUnits: 0,
      flags: ["no_symbol"]
    });
    expect(d.outcome).toBe("empty");
    expect(d.actionLabel).toBeNull();
    expect(d.reason).toContain("没有可处理的交易");
  });
});

describe("每个阶段 × 字段状态都有出口", () => {
  /**
   * 真值表：字段状态（缺代码 / 缺日期 / 两者都缺 / 齐全）× 后端标签 × 净额符号。
   * 断言不是「结果好看」，而是**不存在既没按钮也没原因的格子**——这正是死胡同
   * 弹窗的形态：`needsFill=false` 时表单、步骤、预览、勾选全被 `v-if` 挡掉，
   * 只剩一句开场白和一个禁用按钮。
   */
  const fieldStates: Record<
    string,
    { symbol: string; trade_date: string | null }[]
  > = {
    缺代码: [{ symbol: "", trade_date: "2026-04-16" }],
    缺日期: [{ symbol: "118001", trade_date: null }],
    两者都缺: [{ symbol: "", trade_date: null }],
    齐全: [{ symbol: "118001", trade_date: "2026-04-16" }]
  };
  const flagStates: Record<string, string[]> = {
    无标签: [],
    缺码: ["no_symbol"],
    唯一候选: ["auto_attach_after_enrich"],
    无候选: ["no_candidate"]
  };
  const nets = [-100, 0, 1];

  it("13 组输入全部落在枚举内，且无动作必有原因", () => {
    let checked = 0;
    for (const [fieldName, txns] of Object.entries(fieldStates)) {
      for (const [flagName, flags] of Object.entries(flagStates)) {
        for (const netUnits of nets) {
          const d = unownedOutcome({
            needs: needsOf(txns),
            netUnits,
            flags
          });
          const at = `${fieldName}/${flagName}/net=${netUnits}`;
          expect(OUTCOMES, at).toContain(d.outcome);
          expect(d.reason.trim(), `${at} 没有原因`).not.toBe("");
          // 有动作 ⇒ 有按钮文字；没动作 ⇒ 按钮为空但原因已在上一行断过
          if (d.outcome === "fill" || d.outcome === "rebuild") {
            expect(d.actionLabel, at).toBeTruthy();
          } else {
            expect(d.actionLabel, at).toBeNull();
          }
          checked += 1;
        }
      }
    }
    expect(checked).toBe(
      Object.keys(fieldStates).length *
        Object.keys(flagStates).length *
        nets.length
    );
  });

  it("只有 fill / rebuild 会给出主动作（其余靠删除，不假装有别的路）", () => {
    const labels = new Set<string | null>();
    for (const txns of Object.values(fieldStates)) {
      for (const flags of Object.values(flagStates)) {
        for (const netUnits of nets) {
          labels.add(
            unownedOutcome({
              needs: needsOf(txns),
              netUnits,
              flags
            }).actionLabel
          );
        }
      }
    }
    expect([...labels].filter(Boolean).sort()).toEqual([
      "按流水重建持仓",
      "补全信息"
    ]);
  });
});

describe("净额门槛与后端同一口径（最小单位）", () => {
  it("小于 1 个最小单位（0.0001 份）不算净额为正", () => {
    // 后端 MIN_NET_MIN_UNITS = 1（最小单位）⇒ 0.00005 份 = 0.5 个最小单位，拒绝
    const d = unownedOutcome({
      needs: completeNeeds(),
      netUnits: 0.00005,
      flags: ["no_candidate"]
    });
    expect(d.outcome).toBe("deleteOnly");
  });

  it("恰好 1 个最小单位可以重建（边界不抖动）", () => {
    const d = unownedOutcome({
      needs: completeNeeds(),
      netUnits: 0.0001,
      flags: ["no_candidate"]
    });
    expect(d.outcome).toBe("rebuild");
  });
});

describe("decideDanglingAction：执行区分派（导航名 vs 单组判据）", () => {
  const group = {
    transactions: [{ symbol: "118001", trade_date: "2026-04-16" }],
    net_units: 100,
    flags: ["no_candidate"]
  };

  it("rebuild 阶段：导航名即动作名，并接上重建弹窗", () => {
    const d = decideDanglingAction("rebuild", group, "重建持仓");
    expect(d.unowned).toBeNull();
    expect(d.primaryLabel).toBe("重建持仓");
    expect(d.rebuildTarget).toBe(true);
  });

  it("fill / reattach / mislink：不接重建弹窗（避免按钮点了没有弹窗）", () => {
    for (const stage of ["fill", "reattach", "mislink"] as const) {
      const d = decideDanglingAction(stage, group, "补全信息");
      expect(d.primaryLabel).toBe("补全信息");
      expect(d.rebuildTarget).toBe(false);
    }
  });

  it("unowned 阶段：动作文字读单组判据，不读导航名", () => {
    const positive = decideDanglingAction("unowned", group, "逐组处理");
    expect(positive.primaryLabel).toBe("按流水重建持仓");
    expect(positive.rebuildTarget).toBe(true);

    const negative = decideDanglingAction(
      "unowned",
      { ...group, net_units: -100 },
      "逐组处理"
    );
    expect(negative.primaryLabel).toBeNull();
    expect(negative.rebuildTarget).toBe(false);
    expect(negative.unowned?.reason).toContain("净额");
  });

  it("无阶段 / 无分组：退回导航名，不抛错", () => {
    expect(decideDanglingAction(null, null, "查看").primaryLabel).toBe("查看");
    expect(decideDanglingAction("unowned", null, "逐组处理").primaryLabel).toBe(
      "逐组处理"
    );
  });
});
