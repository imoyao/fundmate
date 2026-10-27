/**
 * 桑基图的布局几何与取色（#980 批 B8 拆出 `sankeyLayout.ts` 时补的网）。
 *
 * 这些函数原先在组件里，只能靠「看一眼图对不对」。而它们决定的都是**肉眼不易
 * 察觉的错**：
 * - 资产节点跑到负债节点下面（分支标记没传播到子节点）；
 * - 某一层节点全被丢掉（BFS 的 visited 判定用了 `undefined`，环里的节点进不了布局）；
 * - 节点流量取成「只有出边」或「只有入边」（取 max 才与 ECharts 的节点粗细一致）；
 * - 负债子项没颜色（映射表查不到时必须按名字兜底成 neutral，否则会变成默认蓝，
 *   在一屏资产色里反而最刺眼——语义正好反了）。
 *
 * 取色通过 `readVar` 注入：真实实现读 `getComputedStyle`，在 jsdom 里恒为空，
 * 直接 import 会让所有用例都落到 fallback 分支，等于没测到映射表。
 */
import { describe, expect, it } from "vitest";
import {
  computeManualLayout,
  computeMaxLevel,
  formatNodeLabel,
  getNodeColor,
  hasDrawableData,
  NODE_COLOR_VARS,
  type SankeyDataNode,
  type SankeyLink
} from "../sankeyLayout";

/** 假 CSS 变量读取器：已知的名字给一个可辨识的色值，未知返回空串（模拟未定义） */
const VARS: Record<string, string> = {
  "--brand-700": "#aabbcc",
  "--color-fall": "#00aa00",
  "--color-neutral": "#888888",
  "--asset-cat-stock": "#111111",
  "--text-tertiary": "#999999"
};
const readVar = (name: string) => VARS[name] ?? "";

const n = (name: string): SankeyDataNode => ({ name });
const l = (source: string, target: string, value: number): SankeyLink => ({
  source,
  target,
  value
});

describe("getNodeColor", () => {
  it("映射表命中时取令牌色", () => {
    expect(getNodeColor("总资产", readVar)).toBe("#aabbcc");
    expect(getNodeColor("股票", readVar)).toBe("#111111");
  });

  it("映射表命中但令牌未定义（读回空串）时继续走兜底", () => {
    // 「流动资金」映射到 --palette-mint-green，VARS 里没有 ⇒ 落到 --text-tertiary
    expect(getNodeColor("流动资金", readVar)).toBe("#999999");
  });

  it("映射表没有的负债子项按名字兜底成 neutral —— 用户自建负债名是常态", () => {
    expect(getNodeColor("房贷", readVar)).toBe("#888888");
    expect(getNodeColor("借家人的钱", readVar)).toBe("#888888");
    expect(getNodeColor("招行信用卡", readVar)).toBe("#888888");
  });

  it("未知且非负债的名字退到三级文字色", () => {
    expect(getNodeColor("某个新节点", readVar)).toBe("#999999");
  });

  it("neutral 也未定义时给一个 CSS 变量兜底，而不是空串（空串会让节点变默认蓝）", () => {
    expect(getNodeColor("房贷", () => "")).toBe("var(--text-tertiary)");
  });

  it("映射表本身不得为空：它是节点着色的唯一来源表", () => {
    expect(Object.keys(NODE_COLOR_VARS).length).toBeGreaterThan(10);
  });
});

describe("computeMaxLevel", () => {
  it("线性链：A → B → C ⇒ 最大层级 2", () => {
    const nodes = [n("A"), n("B"), n("C")];
    const links = [l("A", "B", 1), l("B", "C", 1)];
    expect(computeMaxLevel(nodes, links)).toBe(2);
  });

  it("多源（无入边节点都算第 0 层）", () => {
    const nodes = [n("A"), n("B"), n("C")];
    const links = [l("A", "C", 1), l("B", "C", 1)];
    expect(computeMaxLevel(nodes, links)).toBe(1);
  });

  it("空 nodes ⇒ 0（Math.max 的兜底，不返回 -Infinity）", () => {
    expect(computeMaxLevel([], [])).toBe(0);
  });

  it("全都有入边（环）时从第一个节点起算，不返回负数", () => {
    const nodes = [n("A"), n("B")];
    const links = [l("A", "B", 1), l("B", "A", 1)];
    expect(computeMaxLevel(nodes, links)).toBe(1);
  });
});

describe("computeManualLayout", () => {
  const nodes = [n("总资产"), n("投资理财"), n("总负债"), n("房贷")];
  const links = [
    l("总资产", "投资理财", 100),
    l("总资产", "总负债", 40),
    l("总负债", "房贷", 40)
  ];

  const layout = (chartWidth = 1000, levelCount = 3) =>
    computeManualLayout(nodes, links, chartWidth, levelCount, 100, 80, readVar);

  it("x 坐标 = leftPad + 层级 × 列宽，列宽 = (宽 - 左右内边距) / (层级数 - 1)", () => {
    const { nodes: out } = layout();
    const byName = Object.fromEntries(
      out.map(o => [o.name as string, o as Record<string, number>])
    );
    // (1000 - 100 - 80) / (3 - 1) = 410
    expect(byName["总资产"].x).toBe(100);
    expect(byName["投资理财"].x).toBe(510);
    expect(byName["总负债"].x).toBe(510);
    expect(byName["房贷"].x).toBe(920);
  });

  it("资产分支在上、负债分支在下，中间留出 branchGap", () => {
    const { nodes: out } = layout();
    const asset = out.find(o => o.name === "投资理财") as Record<
      string,
      number
    >;
    const liab = out.find(o => o.name === "总负债") as Record<string, number>;
    // 同层：资产节点先堆（y=20），负债节点额外下移 branchGap - gap = 50
    expect(asset.y).toBe(20);
    expect(liab.y).toBeGreaterThan(asset.y);
  });

  it("分支标记向下传播：名字不像负债的负债后代，靠祖先归属进负债支", () => {
    // 「消费分期」不含 贷/借/信用卡/负债，名字兜底认不出来 —— 只能靠
    // 「总负债」这一支向下传播。同一层里资产先堆、负债让出 branchGap，
    // 因此它必然排在「股票」下方，且 y = 20 + (20+10) + (60-10)。
    const deep = computeManualLayout(
      [n("总资产"), n("投资理财"), n("总负债"), n("股票"), n("消费分期")],
      [
        l("总资产", "投资理财", 100),
        l("总资产", "总负债", 40),
        l("投资理财", "股票", 100),
        l("总负债", "消费分期", 40)
      ],
      1000,
      3,
      100,
      80,
      readVar
    );
    const byName = Object.fromEntries(
      deep.nodes.map(o => [o.name as string, o as Record<string, number>])
    );
    expect(byName["股票"].y).toBe(20);
    expect(byName["消费分期"].y).toBe(100);
  });

  it("节点流量取 max(出边和, 入边和)：与 ECharts 节点粗细一致", () => {
    const { nodes: out } = layout();
    const total = out.find(o => o.name === "总资产") as Record<string, number>;
    // 总资产只有出边 100 + 40 = 140，没有入边
    expect(total.value).toBe(140);
    const liab = out.find(o => o.name === "总负债") as Record<string, number>;
    // 总负债入边 40、出边 40 ⇒ max = 40（不是 80）
    expect(liab.value).toBe(40);
  });

  it("第 0 层的标签在左侧，其余在右侧（首列没有左邻居，标签会压到画布外）", () => {
    const { nodes: out } = layout();
    const total = out.find(o => o.name === "总资产") as any;
    expect(total.label.position).toBe("left");
    const invest = out.find(o => o.name === "投资理财") as any;
    expect(invest.label.position).toBe("right");
  });

  it("maxY 覆盖最靠下的节点，供调用方算容器高度", () => {
    const { maxY } = layout();
    expect(maxY).toBeGreaterThan(20);
  });

  it("层级数为 1 时列宽取整条绘制宽度（不除以 0）", () => {
    const { nodes: out } = computeManualLayout(
      [n("总资产")],
      [],
      1000,
      1,
      100,
      80,
      readVar
    );
    expect((out[0] as Record<string, number>).x).toBe(100);
  });

  it("原始节点字段原样透传（后端可能带额外业务字段给 tooltip 用）", () => {
    const { nodes: out } = computeManualLayout(
      [{ name: "总资产", extra: "keep-me" }],
      [],
      1000,
      1,
      100,
      80,
      readVar
    );
    expect((out[0] as Record<string, unknown>).extra).toBe("keep-me");
  });
});

describe("hasDrawableData", () => {
  it("nodes 与 links 都非空才算可画", () => {
    expect(hasDrawableData({ nodes: [n("A")], links: [l("A", "B", 1)] })).toBe(
      true
    );
  });

  it("任一为空都不画 —— 半张图比空白更让人误解", () => {
    expect(hasDrawableData({ nodes: [], links: [l("A", "B", 1)] })).toBe(false);
    expect(hasDrawableData({ nodes: [n("A")], links: [] })).toBe(false);
    expect(hasDrawableData(null)).toBe(false);
    expect(hasDrawableData(undefined)).toBe(false);
  });

  it("非数组同样不可画（后端异常时给对象而不是数组）", () => {
    expect(hasDrawableData({ nodes: {} as any, links: [] })).toBe(false);
  });
});

describe("formatNodeLabel", () => {
  it("hidden：只留名字（金额打码在 tooltip 里做，标签不出现数字）", () => {
    expect(formatNodeLabel({ name: "总资产", value: 12345 }, "hidden", 0)).toBe(
      "总资产"
    );
  });

  it("amount：≥1 万走「万」，否则千分位原值", () => {
    expect(formatNodeLabel({ name: "股票", value: 123456 }, "amount", 0)).toBe(
      "股票\n¥12.3万"
    );
    expect(formatNodeLabel({ name: "股票", value: 1234 }, "amount", 0)).toBe(
      "股票\n¥1,234"
    );
  });

  it("percent：以「总资产」为分母（不是各节点求和 —— 各层是同一笔钱的不同切法）", () => {
    expect(formatNodeLabel({ name: "股票", value: 25 }, "percent", 100)).toBe(
      "股票\n25.0%"
    );
  });

  it("percent 分母为 0 时给 0%，不出现 NaN / Infinity", () => {
    expect(formatNodeLabel({ name: "股票", value: 0 }, "percent", 0)).toBe(
      "股票\n0%"
    );
  });

  it("value 缺失按 0 处理，不抛错", () => {
    expect(formatNodeLabel({ name: "股票" }, "amount", 0)).toBe("股票\n¥0");
  });
});
