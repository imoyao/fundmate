/**
 * 自选表格「默认列宽预算」守卫（columnDefs 铁律 1 的机器判据）。
 *
 * ## 为什么要有这个文件
 *
 * 铁律 1（`columnDefs.ts` 文件头）写的是「默认可见列总宽有上限」，但在 #2641 之前
 * 它**只存在于注释里**：`trend` 的 `scope` 从 `"mixed"` 被改回去过，注释写着「回到品类
 * 视图专属」而代码写的是 `mixed`，两者分叉近两个月没人发现——因为没有任何东西会因此变红。
 * 结果是默认列 1132px 与文档口径对不上，「1366×768 不出现横向滚动」这条保证静默失效。
 *
 * ⚠️ 这类「文档/注释里有、机器上无」的约束，失效时不产生任何信号。
 * 本文件把它变成判据：改列宽 / 加列 / 改 scope 都会在这里被挡。
 *
 * ## 口径（2026-10-26 修订）
 *
 * 预算从 **1040 放宽到 1132**：owner 拍板「走势列是持仓场景的必看信息，不能为了
 * 不横滚而拿掉」，1366×768 下允许表格内部横向滚动（两端冻结列常驻）。
 * 因此本文件钉的是**上限 1132**，不再断言「默认视图不滚动」。
 *
 * 「混合视图默认可见」= `scope === "mixed"` 且 `!defaultHidden`（`_selection` 除外，
 * 它由模板按 batchMode 条件注入，不计入默认宽度）。
 * 宽度取 `width ?? minWidth`：固定列用 `width`，其余用 `minWidth`（见文件头 1) 条）。
 */
import { describe, expect, it } from "vitest";

import { TRADABLE_TYPES, watchlistColumnDefs } from "../columnDefs";

/**
 * design.md「冻结列与横向滚动规范」：默认可见列总宽上限。
 *
 * 1132 = 232(product) + 96(最新价) + 96(涨跌幅) + 92(走势) + 104(持有数量)
 *        + 140(持仓市值) + 128(持仓收益) + 104(当日盈亏) + 140(操作)。
 * 想加默认列，先改这个值与 columnDefs 文件头，并说明宽度从哪来——不允许静默加宽。
 */
const BUDGET = 1132;

function mixedDefaultColumns() {
  return watchlistColumnDefs.filter(
    d => d.key !== "_selection" && d.scope === "mixed" && !d.defaultHidden
  );
}

function widthOf(d: { width?: number; minWidth?: number }): number {
  return d.width ?? d.minWidth ?? 0;
}

describe("默认列宽预算（铁律 1）", () => {
  it("混合视图默认可见列总宽 ≤ 1132px", () => {
    const cols = mixedDefaultColumns();
    const total = cols.reduce((s, d) => s + widthOf(d), 0);
    // 失败时把账目打出来，否则只看到「1132 !== 1132」不知道该删哪列
    const ledger = cols.map(d => `${d.key}=${widthOf(d)}`).join(" + ");
    expect(total, `${total}px > ${BUDGET}px：${ledger}`).toBeLessThanOrEqual(
      BUDGET
    );
  });

  it("每一列都必须声明宽度（否则上面那条会因 0 宽度假绿）", () => {
    // 如果没有这条，新增一个忘写 width/minWidth 的 mixed 列会让 Σ 变小、
    // 预算守卫依然全绿——「加列不加宽」的假象比不加守卫更糟。
    const missing = watchlistColumnDefs
      .filter(d => d.key !== "_selection")
      .filter(d => widthOf(d) <= 0)
      .map(d => d.key);
    expect(missing).toEqual([]);
  });
});

describe("走势列默认可见（2026-10-26 口径修订）", () => {
  const trend = watchlistColumnDefs.find(d => d.key === "trend")!;

  it("scope 是 mixed：混合视图（自选页默认的「持仓」分组）也要显示", () => {
    // 背景：#2650 曾把它改成 "category" 以守住 1040px，导致持仓分组看不到走势列。
    // owner 拍板：持仓里必然关注持仓产品走势，宁可放宽预算也不能省这一列。
    expect(trend.scope).toBe("mixed");
  });

  it("没有 defaultHidden：不是「靠用户去列设置开回来」", () => {
    expect(trend.defaultHidden).toBeFalsy();
  });

  it("确实进了「混合视图默认可见列」集合，且计入预算账目", () => {
    const keys = mixedDefaultColumns().map(d => d.key);
    expect(keys).toContain("trend");
  });

  it("仍覆盖全部可交易品类（品类视图不因此缩水）", () => {
    expect(trend.appliesTo).toEqual(TRADABLE_TYPES);
  });
});

describe("当日盈亏列（#2640）", () => {
  const dayPnl = watchlistColumnDefs.find(d => d.key === "day_pnl")!;
  const createdAt = watchlistColumnDefs.find(d => d.key === "created_at")!;

  it("默认可见且走派生渲染", () => {
    expect(dayPnl.scope).toBe("mixed");
    expect(dayPnl.defaultHidden).toBeFalsy();
    expect(dayPnl.derived).toBe("dayPnl");
  });

  it("与降为可选的 created_at 等宽（进一出一）", () => {
    expect(createdAt.defaultHidden).toBe(true);
    expect(widthOf(dayPnl)).toBe(widthOf(createdAt));
  });
});
