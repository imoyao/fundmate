/**
 * 桑基图的节点数据、取色与 option 组装（#980 批 B8 拆出 `sankeyLayout.ts` 时补的网，
 * 2026-11-09 按 D94「单轴守恒图」+ 用户认可的参考形态整组重写）。
 *
 * 为什么这些值得单测：ECharts 6 已经没有 `layout: 'none'`，节点位置由自动布局决定，
 * 前端能控制的只剩几件「静默坏掉也看不出报错」的东西——
 * - **节点数组顺序**（自动布局拿它当同列初始上下次序，barycenter 排错就斜穿成 X）；
 * - **node.value**（取 max(出边和, 入边和)，取错则节点粗细与流量带不一致）；
 * - **容器最小高度 / nodeGap**（不够高时标签被压进几 px 厚的节点互相盖住）；
 * - **形态参数**（粗节点 + 大间距 + 带底色两行标签会撑出用户不认可的「多出来一截」）。
 *
 * 取色通过 `readVar` 注入：真实实现读 `getComputedStyle`，在 jsdom 里恒为空，
 * 直接 import 会让所有用例都落到 fallback 分支，等于没测到映射表。
 */
import { describe, expect, it } from "vitest";
import {
  computeSankeyNodes,
  formatNodeLabel,
  getNodeColor,
  hasDrawableData,
  NODE_COLOR_VARS,
  SANKEY_LABEL_HEIGHT,
  SANKEY_MIN_CHART_HEIGHT,
  SANKEY_NODE_GAP,
  type SankeyDataNode,
  type SankeyLink
} from "../sankeyLayout";
import { buildSankeyOption } from "../sankeyOption";

/** 假 CSS 变量读取器：已知的名字给一个可辨识的色值，未知返回空串（模拟未定义） */
const VARS: Record<string, string> = {
  "--brand-700": "#aabbcc",
  "--color-fall": "#00aa00",
  "--color-neutral": "#888888",
  "--palette-periwinkle": "#ab98d1",
  "--asset-cat-stock": "#111111",
  "--text-tertiary": "#999999",
  "--text-primary": "#222222",
  "--text-secondary": "#6b655c",
  "--border-light": "#eeeeee"
};
const readVar = (name: string) => VARS[name] ?? "";

const n = (name: string): SankeyDataNode => ({ name });
const l = (source: string, target: string, value: number): SankeyLink => ({
  source,
  target,
  value
});

/**
 * D94「单轴守恒图」基准拓扑（与用户认可的参考实现同款形状，节点名改用后端
 * `get_sankey_data()` 的真实标签）。列语义：
 *   0 负债明细 / 净资产 → 1 总负债 → 2 总资产 → 3 资产大类 → 4 资产明细
 * 「净资产 → 总资产」是跨两列的长边，这是参考图本身的形态。
 */
const d94Nodes = [
  "房屋贷款(我)",
  "净资产",
  "总负债",
  "总资产",
  "固定资产",
  "流动资金",
  "投资理财",
  "房产（自住）(我)",
  "微众银行(我)",
  "公积金(我)",
  "基金(我)",
  "股票(我)"
].map(n);
const d94Links = [
  l("房屋贷款(我)", "总负债", 380),
  l("总负债", "总资产", 380),
  l("净资产", "总资产", 620),
  l("总资产", "固定资产", 736.7),
  l("总资产", "流动资金", 71),
  l("总资产", "投资理财", 192.2),
  l("固定资产", "房产（自住）(我)", 736.7),
  l("流动资金", "微众银行(我)", 67.2),
  l("流动资金", "公积金(我)", 3.8),
  l("投资理财", "基金(我)", 74.9),
  l("投资理财", "股票(我)", 117.4)
];

const indexOf = (out: Record<string, unknown>[], name: string) =>
  out.findIndex(o => o.name === name);

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
    expect(getNodeColor("花呗", readVar)).toBe("#888888");
  });

  it("未知且非负债的名字退到三级文字色", () => {
    expect(getNodeColor("某个新节点", readVar)).toBe("#999999");
  });

  it("neutral 也未定义时给一个 CSS 变量兜底，而不是空串（空串会让节点变默认蓝）", () => {
    expect(getNodeColor("房贷", () => "")).toBe("var(--text-tertiary)");
  });

  it("明细继承父大类色；自身映射优先于继承（总资产不能被总负债染灰）", () => {
    expect(getNodeColor("自定义明细", readVar, "--palette-periwinkle")).toBe(
      "#ab98d1"
    );
    expect(getNodeColor("总资产", readVar, "--color-neutral")).toBe("#aabbcc");
  });

  it("映射表本身不得为空：它是节点着色的唯一来源表", () => {
    expect(Object.keys(NODE_COLOR_VARS).length).toBeGreaterThan(10);
  });

  it("D94：五笔钱与「未配置资产」已整支删除，映射表里不得再有这些正交轴节点", () => {
    [
      "未配置资产",
      "活钱",
      "稳健底仓",
      "长期增值",
      "高风险博弈",
      "保险保障"
    ].forEach(name => {
      expect(NODE_COLOR_VARS[name]).toBeUndefined();
    });
  });
});

describe("computeSankeyNodes（D94 单轴守恒图）", () => {
  const layout = () => computeSankeyNodes(d94Nodes, d94Links, readVar);

  it("不再输出手算 x/y —— ECharts 6 忽略它们，留着只会让人以为坐标生效", () => {
    const { nodes: out } = layout();
    out.forEach(o => {
      expect(o).not.toHaveProperty("x");
      expect(o).not.toHaveProperty("y");
    });
  });

  it("节点集合不增不减（前端不造节点，守恒由后端保证）", () => {
    const { nodes: out } = layout();
    expect(out.map(o => o.name).sort()).toEqual(
      d94Nodes.map(o => o.name).sort()
    );
  });

  it("首列沿用后端下发顺序：负债明细在上、净资产在下（与参考图一致）", () => {
    const { nodes: out } = layout();
    expect(indexOf(out, "房屋贷款(我)")).toBeLessThan(indexOf(out, "净资产"));
  });

  it("同重心的大类保持后端语义顺序，不被旧 ORDER_WEIGHT 倒成「投资理财优先」", () => {
    const { nodes: out } = layout();
    expect(indexOf(out, "固定资产")).toBeLessThan(indexOf(out, "流动资金"));
    expect(indexOf(out, "流动资金")).toBeLessThan(indexOf(out, "投资理财"));
  });

  it("明细跟随父大类：barycenter 让子节点按父节点上下次序展开", () => {
    const { nodes: out } = layout();
    expect(indexOf(out, "房产（自住）(我)")).toBeLessThan(
      indexOf(out, "微众银行(我)")
    );
    expect(indexOf(out, "公积金(我)")).toBeLessThan(indexOf(out, "基金(我)"));
    expect(indexOf(out, "基金(我)")).toBeLessThan(indexOf(out, "股票(我)"));
  });

  it("节点流量取 max(出边和, 入边和)：与 ECharts 节点粗细一致", () => {
    const { nodes: out } = layout();
    const total = out.find(o => o.name === "总资产") as Record<string, number>;
    // 总资产入边 380 + 620 = 1000，出边 736.7 + 71 + 192.2 = 999.9
    expect(total.value).toBe(1000);
    const liab = out.find(o => o.name === "总负债") as Record<string, number>;
    expect(liab.value).toBe(380);
  });

  it("第 0 层的标签在左侧，其余在右侧，distance 与参考实现一致", () => {
    const { nodes: out } = layout();
    const label = (name: string) =>
      out.find(o => o.name === name)?.label as {
        position: string;
        distance: number;
      };
    expect(label("房屋贷款(我)").position).toBe("left");
    expect(label("净资产").position).toBe("left");
    expect(label("总资产").position).toBe("right");
    expect(label("股票(我)").position).toBe("right");
    expect(label("总资产").distance).toBe(8);
  });

  it("负债资金来源侧走 neutral，资产明细继承大类色", () => {
    const { nodes: out } = layout();
    const color = (name: string) =>
      (out.find(o => o.name === name)?.itemStyle as { color: string }).color;
    expect(color("房屋贷款(我)")).toBe("#888888");
    expect(color("总负债")).toBe("#888888");
    expect(color("股票(我)")).toBe("#ab98d1"); // 继承「投资理财」
    expect(color("总资产")).toBe("#aabbcc"); // 自身映射优先
  });

  it("「负债」别名同样被识别为资金来源侧（参考实现的节点名）", () => {
    const out = computeSankeyNodes(
      ["房贷", "负债", "总资产", "固定资产", "自住房"].map(n),
      [
        l("房贷", "负债", 100),
        l("负债", "总资产", 100),
        l("总资产", "固定资产", 100),
        l("固定资产", "自住房", 100)
      ],
      readVar
    ).nodes;
    const color = (name: string) =>
      (out.find(o => o.name === name)?.itemStyle as { color: string }).color;
    expect(color("房贷")).toBe("#888888");
    expect(color("负债")).toBe("#888888");
  });

  it("原始节点字段原样透传（后端可能带额外业务字段给 tooltip 用）", () => {
    const { nodes: out } = computeSankeyNodes(
      [{ name: "总资产", extra: "keep-me" }],
      [],
      readVar
    );
    expect(out[0].extra).toBe("keep-me");
  });

  it("浅树回落 400px 下限，不是写死的常量", () => {
    const { minHeight } = computeSankeyNodes(
      [n("总资产"), n("基金")],
      [l("总资产", "基金", 100)],
      readVar
    );
    expect(minHeight).toBe(SANKEY_MIN_CHART_HEIGHT);
  });

  it("汇点变多时高度按最密一列撑开：每个节点至少分到「标签行高 + 间距」", () => {
    // 20 个叶子同属第 1 层；20 × (16 + 16) + 40 = 680px
    const leaves = Array.from({ length: 20 }, (_, i) => `叶${i}`);
    const many = computeSankeyNodes(
      [n("总资产"), ...leaves.map(n)],
      leaves.map(name => l("总资产", name, 10)),
      readVar
    );
    expect(many.minHeight).toBe(
      20 * (SANKEY_LABEL_HEIGHT + SANKEY_NODE_GAP) + 40
    );
    expect(many.minHeight).toBeGreaterThan(SANKEY_MIN_CHART_HEIGHT);
  });

  it("nodeGap 必须装得下单行标签，且保持参考实现的紧凑间距（改回 36 会撑出尖楔）", () => {
    expect(SANKEY_NODE_GAP).toBeGreaterThanOrEqual(SANKEY_LABEL_HEIGHT);
    expect(SANKEY_LABEL_HEIGHT).toBe(16);
    expect(SANKEY_NODE_GAP).toBe(16);
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
    expect(
      hasDrawableData({ nodes: {} as unknown as SankeyDataNode[], links: [] })
    ).toBe(false);
  });
});

describe("formatNodeLabel（单行 rich）", () => {
  it("hidden：只留名字，且仍包在 name 样式里（否则会退回节点自动对比色）", () => {
    expect(formatNodeLabel({ name: "总资产", value: 12345 }, "hidden", 0)).toBe(
      "{name|总资产}"
    );
  });

  it("amount：≥1 万走「万」，否则千分位原值；名字与数值同一行", () => {
    expect(formatNodeLabel({ name: "股票", value: 123456 }, "amount", 0)).toBe(
      "{name|股票}  {val|¥12.3万}"
    );
    expect(formatNodeLabel({ name: "股票", value: 1234 }, "amount", 0)).toBe(
      "{name|股票}  {val|¥1,234}"
    );
  });

  it("percent：以「总资产」为分母（不是各节点求和 —— 各层是同一笔钱的不同切法）", () => {
    expect(formatNodeLabel({ name: "股票", value: 25 }, "percent", 100)).toBe(
      "{name|股票}  {val|25.0%}"
    );
  });

  it("percent 分母为 0 时给 0%，不出现 NaN / Infinity", () => {
    expect(formatNodeLabel({ name: "股票", value: 0 }, "percent", 0)).toBe(
      "{name|股票}  {val|0%}"
    );
  });

  it("value 缺失按 0 处理，不抛错", () => {
    expect(formatNodeLabel({ name: "股票" }, "amount", 0)).toBe(
      "{name|股票}  {val|¥0}"
    );
  });

  it("名字里的 { } 会被剔除：它们会破坏 ECharts rich 的标记语法", () => {
    expect(formatNodeLabel({ name: "甲{乙}丙" }, "hidden", 0)).toBe(
      "{name|甲乙丙}"
    );
  });
});

/**
 * 区块交叉守门。
 *
 * ECharts 6 在 `layoutIterations:0` 下，节点纵向位置完全由 `initializeNodeDepth`
 * 决定：同列节点按 `data` 顺序赋 `y = i`。所以**纯函数层面就能把「交叉」变成
 * 一个可断言的数字**：相邻两列之间，若两条边的源端次序与目标端次序相反，
 * 那条流量带就必然斜穿过去。
 *
 * 与 `buildSankeyOption` 的 `layoutIterations` 断言是**成对**的：后者保证上面
 * 这套模拟模型成立，前者保证数组顺序在该模型下不交叉。
 */
describe("区块交叉守门", () => {
  /**
   * 相邻列之间边端点次序相反的对数 = 肉眼可见的斜穿交叉条数。
   *
   * ⚠️ 层级**从 links 独立算**，绝不能读 `out[i].depth`：那是被测代码的输出。
   * 否则一旦有人把 `depth` 删掉，所有节点退化到同一列、计数恒为 0，
   * 这条守门就变成假绿（回退探针实测踩过这个坑）。
   *
   * ⚠️ D94 里「净资产 → 总资产」跨两列，是参考图允许的长边；本检测器只统计
   * **恰好跨一列**的边，长边跳过。所以另有一条「边不倒流」断言兜住方向。
   */
  function countCrossings(
    out: Record<string, unknown>[],
    links: SankeyLink[]
  ): number {
    const indegree = new Map<string, number>();
    out.forEach(o => indegree.set(o.name as string, 0));
    links.forEach(l =>
      indegree.set(l.target, (indegree.get(l.target) ?? 0) + 1)
    );
    const depth = new Map<string, number>();
    const queue: string[] = [];
    out.forEach(o => {
      if (indegree.get(o.name as string) === 0) {
        depth.set(o.name as string, 0);
        queue.push(o.name as string);
      }
    });
    for (let head = 0; head < queue.length; head++) {
      const cur = queue[head];
      links.forEach(l => {
        if (l.source !== cur) return;
        depth.set(
          l.target,
          Math.max(depth.get(l.target) ?? 0, depth.get(cur)! + 1)
        );
        indegree.set(l.target, indegree.get(l.target)! - 1);
        if (indegree.get(l.target) === 0) queue.push(l.target);
      });
    }

    const columns = new Map<number, string[]>();
    out.forEach(o => {
      const d = depth.get(o.name as string) ?? 0;
      if (!columns.has(d)) columns.set(d, []);
      columns.get(d)!.push(o.name as string);
    });
    const rank = new Map<string, number>();
    columns.forEach(names => names.forEach((name, i) => rank.set(name, i)));

    // 必须**按列对分组**：列内序号各列都从 0 开始，跨列对比较 rank 毫无意义。
    const byColumnPair = new Map<number, [number, number][]>();
    links.forEach(link => {
      const srcDepth = depth.get(link.source) ?? -2;
      if (depth.get(link.target) !== srcDepth + 1) return;
      const key = srcDepth;
      if (!byColumnPair.has(key)) byColumnPair.set(key, []);
      byColumnPair
        .get(key)!
        .push([rank.get(link.source)!, rank.get(link.target)!]);
    });

    let crossings = 0;
    byColumnPair.forEach(edges => {
      for (let i = 0; i < edges.length; i++) {
        for (let j = i + 1; j < edges.length; j++) {
          const [s1, t1] = edges[i];
          const [s2, t2] = edges[j];
          if ((s1 < s2 && t1 > t2) || (s1 > s2 && t1 < t2)) crossings++;
        }
      }
    });
    return crossings;
  }

  it("D94 真实拓扑下流量带交叉数为 0（左右平行分层）", () => {
    const { nodes: out } = computeSankeyNodes(d94Nodes, d94Links, readVar);
    expect(countCrossings(out, d94Links)).toBe(0);
  });

  it("检测器本身有效：手工打乱大类列会数出交叉，不是恒返回 0", () => {
    const out = computeSankeyNodes(d94Nodes, d94Links, readVar).nodes;
    // 对调第 3 列的首尾两个大类，子节点不再跟随父节点
    const i = out.findIndex(o => o.name === "固定资产");
    const j = out.findIndex(o => o.name === "投资理财");
    [out[i], out[j]] = [out[j], out[i]];
    expect(countCrossings(out, d94Links)).toBeGreaterThan(0);
  });

  it("所有边方向向右（不倒流）；长边允许但不允许跨回左侧", () => {
    const { nodes: out } = computeSankeyNodes(d94Nodes, d94Links, readVar);
    const depth = new Map(out.map(o => [o.name as string, o.depth as number]));
    d94Links.forEach(link => {
      expect(depth.get(link.target)!).toBeGreaterThan(
        depth.get(link.source) ?? -2
      );
    });
  });

  it("节点带显式 depth 且等于最长路径层级（不是 BFS 首访层级）", () => {
    const { nodes: out } = computeSankeyNodes(d94Nodes, d94Links, readVar);
    const depthOf = (name: string) =>
      out.find(o => o.name === name)?.depth as number;
    expect(depthOf("房屋贷款(我)")).toBe(0);
    expect(depthOf("净资产")).toBe(0);
    expect(depthOf("总负债")).toBe(1);
    expect(depthOf("总资产")).toBe(2);
    expect(depthOf("投资理财")).toBe(3);
    expect(depthOf("股票(我)")).toBe(4);
  });

  it("每个节点都带显式 depth：option 用 justify 时汇点才不会被 moveSinksRight 推走", () => {
    const { nodes: out } = computeSankeyNodes(d94Nodes, d94Links, readVar);
    expect(out.every(o => typeof o.depth === "number")).toBe(true);
  });

  it("后端乱序下发时子节点仍跟随父节点：只按原始顺序排会在这里交叉", () => {
    const links = [
      l("总资产", "甲账户", 60),
      l("总资产", "乙账户", 40),
      l("甲账户", "甲子项", 60),
      l("乙账户", "乙子项", 40)
    ];
    const out = computeSankeyNodes(
      [n("总资产"), n("甲账户"), n("乙账户"), n("乙子项"), n("甲子项")],
      links,
      readVar
    ).nodes;
    const at = (name: string) => out.findIndex(o => o.name === name);
    expect(at("甲子项")).toBeLessThan(at("乙子项"));
    expect(countCrossings(out, links)).toBe(0);
  });
});

/** option 守门：这些字段改坏了图照样画得出来，只是标签重叠 / 又冒出尖楔 */
describe("buildSankeyOption（参考形态）", () => {
  const option = () =>
    buildSankeyOption({
      links: [l("总资产", "基金", 100)],
      layoutNodes: computeSankeyNodes(
        [n("总资产"), n("基金")],
        [l("总资产", "基金", 100)],
        readVar
      ).nodes,
      displayMode: "amount",
      totalValue: 100,
      leftPad: 130,
      rightPad: 190,
      readVar
    });
  const series = () => option().series[0] as unknown as Record<string, unknown>;

  it("不写 layout:'none' —— ECharts 6 已移除该选项，写了是无效配置", () => {
    expect(series().layout).toBeUndefined();
  });

  it("nodeAlign:'justify' + 每个节点显式 depth：汇点不会被推到最后一列", () => {
    expect(series().nodeAlign).toBe("justify");
    expect(series().draggable).toBe(false);
  });

  it("layoutIterations:0 —— 默认 32 次重心松弛会破坏 barycenter 排好的次序", () => {
    expect(series().layoutIterations).toBe(0);
  });

  it("细节点 + 小间距：粗节点 / 大间距是「多出来一截」的成因", () => {
    expect(series().nodeWidth).toBe(7);
    expect(series().nodeGap).toBe(SANKEY_NODE_GAP);
    expect(series().nodeGap).toBeGreaterThanOrEqual(SANKEY_LABEL_HEIGHT);
    expect(series().itemStyle).toEqual({ borderWidth: 0 });
  });

  it("流量带半透明渐变 + 参考实现的曲率", () => {
    expect(series().lineStyle).toEqual({
      color: "gradient",
      curveness: 0.5,
      opacity: 0.42
    });
  });

  it("标签是单行 rich，两种文字色都显式给（不靠 ECharts 按节点色自动挑）", () => {
    const label = series().label as unknown as Record<string, unknown>;
    expect(label.position).toBe("right");
    expect(label.distance).toBe(8);
    expect(label.color).toBe("#222222");
    expect(label.rich).toEqual({
      name: { fontSize: 12, color: "#222222" },
      val: { fontSize: 12, color: "#6b655c", fontWeight: 700 }
    });
  });

  it("不再有背景块 / width / overflow / 两行 lineHeight：它们会把标签撑成白长条盖住流量带", () => {
    const label = series().label as unknown as Record<string, unknown>;
    [
      "backgroundColor",
      "padding",
      "borderRadius",
      "width",
      "overflow",
      "lineHeight"
    ].forEach(key => expect(label[key]).toBeUndefined());
  });

  it("formatter 输出与 formatNodeLabel 一致，且返回 rich 标记而不是纯文本", () => {
    const label = option().series[0].label;
    expect(label.formatter({ name: "股票", value: 123456 })).toBe(
      "{name|股票}  {val|¥12.3万}"
    );
    expect(label.formatter({ name: "股票", value: 123456 })).toBe(
      formatNodeLabel({ name: "股票", value: 123456 }, "amount", 100)
    );
  });

  it("left / right 给单行长标签留够空间", () => {
    expect(series().left).toBe(130);
    expect(series().right).toBe(190);
  });
});
