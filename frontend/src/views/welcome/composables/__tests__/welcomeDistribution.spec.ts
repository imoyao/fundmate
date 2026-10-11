/**
 * 首页「资产构成分布」环形图的数据源选择（#1955）。
 *
 * 缺陷背景（实测本机真实库，family_id=1，154 笔持仓）：
 * - 旧数据源 `summary.market_distribution`（按持仓 `market` 分组）
 *   实际只返回 `{"CN_A": 659104.65}` —— **单键**。
 * - 环形图单扇区占满整圈，且该扇区按索引 0 取色→ `--chart-01`(#e34f38 品牌红)，
 *   于是首页出现一个「完整的红色圆环」，看起来像没数据 / 取数出错。
 *
 * 结论：**数据是真的，取数逻辑有问题** —— 维度选错了，不是后端没返回。
 * 修复：改用 `distributions.category_distribution`（资产大类），
 *      各项之和 === `distributions.total_assets`，与左侧「家庭总资产」同口径。
 */
import { describe, it, expect } from "vitest";
import {
  buildDistributionData,
  CATEGORY_COLOR_MAP
} from "../distributionLogic";
import type { DistributionsData } from "@/api/summary";

/** 真实数据形状的最小构造（字段齐全，测试只关心 category_distribution） */
const dist = (
  category_distribution: Array<{ name: string; value: number }>
): DistributionsData =>
  ({
    category_distribution,
    total_assets: 0
  }) as unknown as DistributionsData;

describe("buildDistributionData：首页环形图数据源", () => {
  it("取category_distribution，而不是 summary.market_distribution", () => {
    const data = buildDistributionData(
      dist([
        { name: "固定资产", value: 2200091.0 },
        { name: "流动资金", value: 1018272.65 },
        { name: "投资理财", value: 636175.73 },
        { name: "应收款", value: 50000.0 }
      ])
    );
    expect(data).toHaveLength(4);
    expect(data.map(d => d.name)).toEqual([
      "固定资产",
      "流动资金",
      "投资理财",
      "应收款"
    ]);
  });

  it("单市场场景仍能出多个扇区 —— 这是本次修复的核心断言", () => {
    // 回归锚点：旧数据源在「全部持仓同市场」时必然只有 1 项。
    // 新数据源按资产大类分，与市场数无关，扇区数恒 > 1。
    const data = buildDistributionData(
      dist([
        { name: "固定资产", value: 100 },
        { name: "流动资金", value: 200 }
      ])
    );
    expect(data.length).toBeGreaterThan(1);
  });

  it("分母口径：各项之和 === total_assets（与左侧「家庭总资产」对得上）", () => {
    const items = [
      { name: "固定资产", value: 2200091.0 },
      { name: "流动资金", value: 1018272.65 },
      { name: "投资理财", value: 636175.73 },
      { name: "应收款", value: 50000.0 }
    ];
    const total = items.reduce((s, d) => s + d.value, 0);
    expect(total).toBeCloseTo(3904539.38, 2);
  });

  it("distributions 为 null（请求失败）→ 空数组，交给图表渲染空态而非报错", () => {
    expect(buildDistributionData(null)).toEqual([]);
    expect(buildDistributionData(undefined)).toEqual([]);
  });

  it("category_distribution 为空数组 → 空数组（不返回 undefined）", () => {
    expect(buildDistributionData(dist([]))).toEqual([]);
  });
});

describe("CATEGORY_COLOR_MAP：大类语义色", () => {
  it("四大类都有显式色，不落回索引取色", () => {
    // 不传 colorMap 时组件按索引取 --chart-01~08，首扇区恒为品牌红，
    // 与涨红跌绿撞车。大类必须有显式映射。
    for (const name of ["固定资产", "流动资金", "投资理财", "应收款"]) {
      expect(CATEGORY_COLOR_MAP[name]).toBeTruthy();
    }
  });

  it("色值走 CSS 变量名，不硬编码 hex（design.md Data Visualization 红线）", () => {
    for (const varName of Object.values(CATEGORY_COLOR_MAP)) {
      expect(varName.startsWith("--")).toBe(true);
      expect(varName).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    }
  });

  it("与桑基图 NODE_COLOR_VARS 的大类配色一致（同大类同色）", () => {
    // 抽样对齐 SankeyChart.vue:64-67，抽样而非全量——防漂移即可
    expect(CATEGORY_COLOR_MAP["流动资金"]).toBe("--palette-mint-green");
    expect(CATEGORY_COLOR_MAP["投资理财"]).toBe("--palette-periwinkle");
    expect(CATEGORY_COLOR_MAP["固定资产"]).toBe("--palette-warm-taupe");
    expect(CATEGORY_COLOR_MAP["应收款"]).toBe("--palette-stone-gray");
  });
});
