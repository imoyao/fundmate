/**
 * 自选表格「默认列宽预算」守卫（columnDefs 铁律 1 的机器判据）。
 *
 * ## 为什么要有这个文件
 *
 * 铁律 1（`columnDefs.ts` 文件头）写的是「默认可见列总宽有上限」，但在 #2641 之前
 * 它**只存在于注释里**：`trend` 的 `scope` 从 `"mixed"` 被改回去过，注释写着「回到品类
 * 视图专属」而代码写的是 `mixed`，两者分叉近两个月没人发现——因为没有任何东西会因此变红。
 *
 * ⚠️ 这类「文档/注释里有、机器上无」的约束，失效时不产生任何信号。
 * 本文件把它变成判据：改列宽 / 加列 / 改 scope 都会在这里被挡。
 *
 * ## 口径沿革（三次修订，别再拿旧数字对账）
 *
 * | 时间 | 上限 | 实测总宽 | 触发 |
 * |---|---|---|---|
 * | #2641 前 | 1040 | 1132 | 走势列恢复 mixed、含 96px「今日涨跌幅」列 |
 * | #2641 后 | 1040 | 1036→984 | 删掉 96px 涨跌幅列；2026-11-02 操作列 140→88 |
 * | **2026-11-05（现行）** | **1088** | **1088** | 「当日盈亏 / 昨日盈亏」拆成两列常驻 |
 *
 * 2026-11-05 owner 明确拍板：**两列都要默认可见，接受 1366 屏表格内部横向滚动**。
 * 于是新增 `yesterday_pnl`（104px）且**不**按铁律 1 的「进一出一」减掉另一列——
 * 减掉任何一列都会破坏「一个今天、一个昨天，一眼分得清」这个产品诉求。
 * 预算因此由 1040 提到 1088（= 984 + 104），**余量用满**。要再加默认列，
 * 必须先改本值与 `columnDefs.ts` 文件头并说明宽度从哪来，不允许静默加宽。
 *
 * 「混合视图默认可见」= `scope === "mixed"` 且 `!defaultHidden`（`_selection` 除外，
 * 它由模板按 batchMode 条件注入，不计入默认宽度）。
 * 宽度取 `width ?? minWidth`：固定列用 `width`，其余用 `minWidth`（见文件头 1) 条）。
 */
import { describe, expect, it } from "vitest";

import { TRADABLE_TYPES, watchlistColumnDefs } from "../columnDefs";

/**
 * design.md「冻结列与横向滚动规范」：默认可见列总宽上限（2026-11-05 拆列后）。
 *
 * 1088 = 232(product) + 104(当日盈亏) + 104(昨日盈亏) + 96(最新价) + 92(走势)
 *       + 104(持有数量) + 140(持仓市值) + 128(持仓收益) + 88(操作)。
 * 相比 2026-11-02 的 984 只多了新增的「昨日盈亏」104px —— 其余列宽一律没动。
 * 想加默认列，先改这个值与 columnDefs 文件头，并说明宽度从哪来——不允许静默加宽。
 */
const BUDGET = 1088;

function mixedDefaultColumns() {
  return watchlistColumnDefs.filter(
    d => d.key !== "_selection" && d.scope === "mixed" && !d.defaultHidden
  );
}

function widthOf(d: { width?: number; minWidth?: number }): number {
  return d.width ?? d.minWidth ?? 0;
}

describe("默认列宽预算（铁律 1）", () => {
  it("混合视图默认可见列总宽 ≤ 1088px", () => {
    const cols = mixedDefaultColumns();
    const total = cols.reduce((s, d) => s + widthOf(d), 0);
    // 失败时把账目打出来，否则只看到「1088 !== 1088」不知道该删哪列
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

  it("两列盈亏都在默认集里（缺一列就说明拆列被回退了）", () => {
    const keys = mixedDefaultColumns().map(d => d.key);
    expect(keys).toContain("day_pnl");
    expect(keys).toContain("yesterday_pnl");
    // 相邻并排：一个今天、一个昨天，中间夹别的列就分不清了
    expect(keys.indexOf("yesterday_pnl")).toBe(keys.indexOf("day_pnl") + 1);
  });
});

describe("走势列默认可见（2026-10-26 口径修订）", () => {
  const trend = watchlistColumnDefs.find(d => d.key === "trend")!;

  it("scope 是 mixed：混合视图（自选页默认的「持仓」分组）也要显示", () => {
    // 背景：#2650 曾把它改成 "category" 以守住当时的 1040px，导致持仓分组看不到走势列。
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

/**
 * 复合列的「口径徽标 + 两档排序」（2026-10-30 二次优化）。
 *
 * 这两条都是**体验约束而非视觉偏好**：徽标不声明 → 用户永远不知道当前按哪一行数排；
 * 排序留三档 → 升/降切换要多点一次、中间还会整表跳回默认序。
 * 拆列后复合列由 3 个变 4 个（当日盈亏 / 昨日盈亏 / 持仓市值 / 持仓收益），
 * 徽标必须塞进各自的 104px 列宽（见 `sortMetric.ts` 为什么用单字符）。
 */
describe("复合列：口径徽标与两档排序", () => {
  const compositeKeys = [
    "day_pnl",
    "yesterday_pnl",
    "position_market_value",
    "holding_pnl"
  ];

  it("四个复合列都声明了 sortMetrics（表头常驻口径徽标）", () => {
    for (const key of compositeKeys) {
      const def = watchlistColumnDefs.find(d => d.key === key);
      expect(def?.sortMetrics, `${key} 缺 sortMetrics`).toBeTruthy();
      expect(def?.sortMetrics?.labels.amount).toBeTruthy();
      expect(def?.sortMetrics?.labels.ratio).toBeTruthy();
    }
  });

  it("复合列排序只有两档：每次点击都换方向，不夹「取消」", () => {
    for (const key of compositeKeys) {
      const def = watchlistColumnDefs.find(d => d.key === key);
      expect(def?.sortOrders, `${key} 的 sortOrders`).toEqual([
        "descending",
        "ascending"
      ]);
    }
  });
});

describe("当日盈亏 / 昨日盈亏两列（#2640 → 2026-11-05 拆列）", () => {
  const today = watchlistColumnDefs.find(d => d.key === "day_pnl")!;
  const yesterday = watchlistColumnDefs.find(d => d.key === "yesterday_pnl")!;
  const createdAt = watchlistColumnDefs.find(d => d.key === "created_at")!;

  it("两列都默认可见、各走各的派生渲染", () => {
    for (const def of [today, yesterday]) {
      expect(def.scope).toBe("mixed");
      expect(def.defaultHidden).toBeFalsy();
      expect(def.renderer).toBe("moneyRatio");
    }
    expect(today.derived).toBe("todayEstimate");
    expect(yesterday.derived).toBe("yesterdayPnl");
    // 两列共用同一个 derived 就会显示同一个数 —— 拆列的核心回归点
    expect(today.derived).not.toBe(yesterday.derived);
  });

  it("三列等宽（104）；进一出一在此被 owner 拍板打破", () => {
    // #2640 用 created_at 换 day_pnl（进一出一）。2026-11-05 新增 yesterday_pnl 时
    // **没有**再减一列：两列必须并排常驻，故预算 984 → 1088、接受表格内部横滚。
    expect(createdAt.defaultHidden).toBe(true);
    expect(widthOf(today)).toBe(104);
    expect(widthOf(yesterday)).toBe(104);
    expect(widthOf(createdAt)).toBe(104);
  });
});
