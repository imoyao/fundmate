/**
 * 桑基图的节点数据、取色与最小绘图高度（#980 批 B8 从 `Charts/SankeyChart.vue` 抽出）。
 *
 * ⚠️ ECharts 6.x 已删除 sankey 的 `layout: 'none'`：`SankeySeriesOption` 里没有
 * `layout` 字段，`sankeyLayout` 无条件跑自动布局，源码也不读 `data[i].x / y`
 * （只认可选的 `item.depth` 和拖拽用的 `localX / localY`）。旧实现手算的 x/y 是死数据。
 *
 * ECharts 自动布局实际只看三件事：
 *   ① `data` 数组顺序 —— `initializeNodeDepth` 给同列节点赋 `y = i`，
 *      **数组顺序就是同列上下次序**；
 *   ② `node.value` 与 `links` —— 决定节点厚度、流量带；
 *   ③ `item.depth`（可选）—— 指定列；`nodeAlign:'justify'` 的 `moveSinksRight()`
 *      只推「没有显式 depth 且无出边」的汇点。
 *
 * ⚠️ 2026-11-09 D94「单轴守恒图」：后端 `get_sankey_data()` 改为
 *
 *       负债明细 → 总负债 ┐
 *       净资产   ─────────┴ → 总资产 → 资产大类 → 资产明细
 *
 *    只承载「资金来源 → 资产运用」一条分类轴，`A = L + E` 逐节点守恒。旧拓扑
 *    （资产形态 → 总资产 → 净资产 / 总负债 → 五笔钱 → 产品类型）下写死的
 *    `branchMap`（沿**出边**传播负债）与 `ORDER_WEIGHT`（五笔钱顺序）在新方向里
 *    会把整张图误标成负债、并把大类顺序倒过来，已全部删除；五笔钱与
 *    「未配置资产」这些正交轴节点也不再出现在图上。
 *
 *    现在节点顺序只靠两件事：
 *      - barycenter：逐列按「父节点在上一列的序号均值」排序，子节点跟随父节点，
 *        流量带才左右平行、不斜穿；
 *      - 后端下发顺序：同重心时的稳定兜底。后端已按列从左到右、列内按语义
 *        （负债明细 / 净资产 → 总负债 → 总资产 → 固定资产 / 流动资金 / 投资理财
 *        → 明细）排好，所以同重心即保持参考图顺序，结果可复现。
 *
 * ⚠️ 形态对齐用户认可的参考实现（`nodeWidth:7 / nodeGap≈14 / nodeAlign:'justify' /
 *    layoutIterations:0 / curveness:0.5 / opacity:0.42 / 单行 rich 标签`）。
 *    2×2 受控对照实验的结论：**X 形斜穿由节点顺序造成，尖楔「多出来一截」由渲染
 *    配置造成，两者独立**。`justify` 在这里是安全的 —— 本文件给**每个**节点都写了
 *    显式 `depth`，`moveSinksRight()` 的 `!isNodeDepth(node)` 会跳过全部汇点；
 *    `layoutIterations:0` 关掉重心松弛，节点上下位置才完全由上面的排序决定。
 *
 * `minHeight` 判据仍是「最密一列的节点数」：容器不够高时 ECharts 把节点压成细条，
 * 单行标签会互相盖住；每个节点至少预留「标签行高 + nodeGap」。
 *
 * 取色通过 `readVar` 注入而不是直接 import `getCssVar`：后者要读
 * `getComputedStyle(document.documentElement)`，在 jsdom 里恒为空串，单测会全部
 * 退化成 fallback 分支，等于没测到映射表。
 */

/** 后端下发的节点（`name` 是布局的唯一键，其余字段原样透传给 ECharts） */
export type SankeyDataNode = { name: string; [key: string]: unknown };

/** 后端下发的连线 */
export type SankeyLink = { source: string; target: string; value: number };

/** 读一个 CSS 变量（生产环境传 `getCssVar`，单测传假实现） */
export type VarReader = (varName: string) => string;

/**
 * 节点名 → CSS 变量名。
 *
 * 标签与后端**同源**：大类取 `ASSET_CATEGORY_LABELS`，产品明细取 `ASSET_TYPE_LABELS`。
 * 「保险 / 房产 / 贵金属」既可能是大类也可能是产品类型标签，共用一套色，别写重复键。
 * 明细节点若不在表里，会继承父大类色（见 `computeSankeyNodes`），与参考图的
 * 「基金 / 股票跟投资理财同色系」一致。
 */
export const NODE_COLOR_VARS: Record<string, string> = {
  // 资金来源与汇总节点
  总资产: "--brand-700",
  净资产: "--color-fall",
  总负债: "--color-neutral",
  负债: "--color-neutral",
  // 资产大类（ASSET_CATEGORY_LABELS）
  流动资金: "--palette-mint-green",
  固定资产: "--palette-warm-taupe",
  投资理财: "--palette-periwinkle",
  应收款: "--palette-stone-gray",
  自定义: "--palette-stone-gray",
  // 大类 / 产品类型同名
  保险: "--color-accent",
  房产: "--palette-warm-taupe",
  贵金属: "--palette-warm-taupe",
  其他: "--palette-stone-gray",
  其他资产: "--palette-stone-gray",
  // 产品类型明细（ASSET_TYPE_LABELS）
  股票: "--asset-cat-stock",
  基金: "--asset-cat-fund",
  ETF: "--asset-cat-etf",
  可转债: "--asset-cat-bond",
  指数: "--asset-cat-index",
  加密货币: "--asset-cat-crypto",
  基金经理: "--asset-cat-fund",
  投顾组合: "--asset-cat-fund",
  货币基金: "--asset-cat-saving",
  逆回购: "--asset-cat-bond",
  银行理财: "--asset-cat-fund",
  现金: "--asset-cat-saving",
  银行存款: "--asset-cat-saving",
  // 账外类现金明细
  "货基/逆回购净额": "--asset-cat-saving",
  渠道收益: "--color-rise"
};

/** 负债类节点名的兜底正则（映射表里没有的负债子项走 neutral） */
const LIABILITY_NAME_RE = /贷|借|信用卡|负债|花呗|白条|分期/;

/**
 * 节点颜色：先查映射表（或继承父大类色），再按负债语义兜底，最后退到三级文字色。
 *
 * `inheritVar` 由 `computeSankeyNodes` 从父节点传入：明细节点不必逐一登记也能与
 * 所属大类同色。映射表自身永远优先，避免「总资产」被「总负债」染成灰色。
 */
export function getNodeColor(
  name: string,
  readVar: VarReader,
  inheritVar?: string
): string {
  const varName = NODE_COLOR_VARS[name] || inheritVar;
  if (varName) {
    const color = readVar(varName);
    if (color) return color;
  }
  if (LIABILITY_NAME_RE.test(name)) {
    return readVar("--color-neutral") || "var(--text-tertiary)";
  }
  return readVar("--text-tertiary");
}

/** 单行标签（fontSize 12 的实际行高）占的像素高度 */
export const SANKEY_LABEL_HEIGHT = 16;

/**
 * ECharts `nodeGap`（同列相邻节点矩形的最小间距）。
 *
 * 标签垂直居中于节点矩形，相邻标签中心距 ≥ nodeGap，所以它必须 ≥ 单行标签行高，
 * 否则相邻标签必然重叠。参考实现用 14，这里留 2px 余量防止 12px 字体行高溢出。
 * option 与容器高度共用这一个常量，改间距时不会出现「option 加了、容器没撑开」的分叉。
 */
export const SANKEY_NODE_GAP = 16;

/** 容器高度下限（与 e2e 的浅树用例约定一致） */
export const SANKEY_MIN_CHART_HEIGHT = 400;

/** option 的 top/bottom 各 12px，再留 16px 余量 */
const CHART_VERTICAL_PAD = 40;

/**
 * 生成 ECharts 节点数据与最小绘图高度。
 *
 * 不再输出 x/y（ECharts 6 忽略）。**数组顺序就是布局语义**：按最长路径拓扑层级
 * 分组，逐列用 barycenter（父节点在上一列的序号均值）排序，同重心保持后端原始
 * 顺序。每个节点都带显式 `depth`，列位置不依赖 ECharts 自动推断。
 *
 * 注意 D94 拓扑里「净资产 → 总资产」是**跨两列的长边**（总负债在第 1 列），
 * 这是参考图本身的形态（绿色权益带直接汇入总资产），不是错误；交叉守门按
 * 「列对」统计时只统计恰好跨一列的边，长边会被跳过。
 */
export function computeSankeyNodes(
  nodes: SankeyDataNode[],
  links: SankeyLink[],
  readVar: VarReader
): { nodes: Record<string, unknown>[]; minHeight: number } {
  const outAdj: Record<string, string[]> = {};
  const inAdj: Record<string, string[]> = {};
  nodes.forEach(n => {
    outAdj[n.name] = [];
    inAdj[n.name] = [];
  });
  links.forEach(l => {
    outAdj[l.source]?.push(l.target);
    inAdj[l.target]?.push(l.source);
  });

  /**
   * 拓扑层级用**最长路径**（父层级 + 1 取最大），与 ECharts
   * `computeNodeBreadths` 里 indegree 归零那套一致。旧的「BFS 首访即赋值」是
   * 最短路径，多父节点会被分到偏左列，barycenter 就会拿错误的列算重心。
   */
  const indegree: Record<string, number> = {};
  nodes.forEach(n => {
    indegree[n.name] = inAdj[n.name].length;
  });
  const nodeLevel: Record<string, number> = {};
  const queue: string[] = [];
  nodes.forEach(n => {
    if (indegree[n.name] === 0) {
      nodeLevel[n.name] = 0;
      queue.push(n.name);
    }
  });
  if (queue.length === 0 && nodes.length > 0) {
    // 全环 / 无零入度节点：ECharts 会抛 "Sankey is a DAG"，这里退到单列避免崩
    nodeLevel[nodes[0].name] = 0;
    queue.push(nodes[0].name);
  }
  let head = 0;
  while (head < queue.length) {
    const curr = queue[head++];
    (outAdj[curr] || []).forEach(next => {
      nodeLevel[next] = Math.max(nodeLevel[next] ?? 0, nodeLevel[curr] + 1);
      indegree[next] -= 1;
      if (indegree[next] === 0) queue.push(next);
    });
  }
  // 环内 / 后端漏发的节点兜底到 0 列，保证每个节点都有列可放
  nodes.forEach(n => {
    if (nodeLevel[n.name] === undefined) nodeLevel[n.name] = 0;
  });

  /**
   * 负债只在**资金来源侧**（D94）：从「总负债」沿**入边**回溯出负债明细。
   * 旧版沿出边传播是旧拓扑（负债在右侧）的假设，新方向下会把总资产与全部
   * 资产大类染成灰色。
   */
  const liabilitySources = new Set<string>();
  const backStack = ["总负债", "负债"];
  while (backStack.length) {
    const cur = backStack.pop()!;
    if (liabilitySources.has(cur)) continue;
    liabilitySources.add(cur);
    (inAdj[cur] || []).forEach(parent => backStack.push(parent));
  }

  const outFlow: Record<string, number> = {};
  const inFlow: Record<string, number> = {};
  nodes.forEach(n => {
    outFlow[n.name] = 0;
    inFlow[n.name] = 0;
  });
  links.forEach(l => {
    outFlow[l.source] = (outFlow[l.source] || 0) + l.value;
    inFlow[l.target] = (inFlow[l.target] || 0) + l.value;
  });
  const nodeFlow: Record<string, number> = {};
  nodes.forEach(n => {
    nodeFlow[n.name] = Math.max(outFlow[n.name], inFlow[n.name]);
  });

  const levelGroups = Object.entries(nodeLevel).reduce(
    (acc, [name, lvl]) => {
      if (!acc[lvl]) acc[lvl] = [];
      acc[lvl].push(name);
      return acc;
    },
    {} as Record<number, string[]>
  );

  const layouted: Record<string, unknown>[] = [];
  /** 节点在**自己那一列**里的序号，供下一列算 barycenter */
  const columnIndex: Record<string, number> = {};
  /** 后端原始顺序：所有排序的最后一道稳定兜底，保证结果可复现 */
  const sourceIndex = new Map(nodes.map((n, i) => [n.name, i]));
  const levels = Object.keys(levelGroups)
    .map(Number)
    .sort((a, b) => a - b);

  const bySourceOrder = (a: string, b: string) =>
    (sourceIndex.get(a) ?? 0) - (sourceIndex.get(b) ?? 0);

  levels.forEach(lvl => {
    const names = levelGroups[lvl];
    const barycenter = (name: string) => {
      const parents = inAdj[name] || [];
      if (!parents.length) return Number.POSITIVE_INFINITY;
      return (
        parents.reduce((sum, p) => sum + (columnIndex[p] ?? 0), 0) /
        parents.length
      );
    };
    // 首列没有父节点可对齐，直接沿用后端下发顺序（负债明细在上 / 净资产在下）
    const ordered = [...names].sort((a, b) => {
      if (lvl === 0) return bySourceOrder(a, b);
      const ca = barycenter(a);
      const cb = barycenter(b);
      if (Number.isFinite(ca) && Number.isFinite(cb) && ca !== cb) {
        return ca - cb;
      }
      // 同重心：保持后端列内语义顺序（固定资产 / 流动资金 / 投资理财 …）
      return bySourceOrder(a, b);
    });

    ordered.forEach((name, i) => {
      columnIndex[name] = i;
      const rawNode = nodes.find(n => n.name === name)!;
      const parents = inAdj[name] || [];
      const inheritVar = parents.map(p => NODE_COLOR_VARS[p]).find(Boolean);
      const color = liabilitySources.has(name)
        ? readVar("--color-neutral") || "var(--text-tertiary)"
        : getNodeColor(name, readVar, inheritVar);
      layouted.push({
        ...rawNode,
        name,
        value: nodeFlow[name] || 0,
        // 显式锁定列位置：既让拓扑语义不依赖 ECharts 自动推断，
        // 也让 `moveSinksRight` 因 isNodeDepth 为真而跳过汇点
        depth: lvl,
        itemStyle: { color },
        label: {
          position: lvl === 0 ? "left" : "right",
          distance: 8
        }
      });
    });
  });

  // 汇点留在各自拓扑层，最密一列就是层节点数的最大值
  const maxLevelNodes = Math.max(
    0,
    ...Object.values(levelGroups).map(group => group.length)
  );
  const minHeight = Math.max(
    SANKEY_MIN_CHART_HEIGHT,
    maxLevelNodes * (SANKEY_LABEL_HEIGHT + SANKEY_NODE_GAP) + CHART_VERTICAL_PAD
  );

  return { nodes: layouted, minHeight };
}

/** 数据是否可画：nodes/links 都非空（任一为空都只出空态，不画全 0 的空图） */
export function hasDrawableData(
  data: { nodes?: unknown[]; links?: unknown[] } | null | undefined
): boolean {
  return (
    !!data &&
    Array.isArray(data.nodes) &&
    Array.isArray(data.links) &&
    data.nodes.length > 0 &&
    data.links.length > 0
  );
}

/**
 * 单行 rich 标签文案：`{name|名称}  {val|金额}`。
 *
 * 与参考实现一致：名字与数值**同一行**、用 rich 分别上色，不要再加背景块
 * ——两块白底长条会盖住流量带，正是用户不认可的「多出来一截」的一部分。
 * 可读性靠**显式文字色**保证（ECharts 按节点色自动挑对比色才会出白字压浅带）。
 * `percent` 的百分比以「总资产」节点的值为分母（各层是同一笔钱的不同切法，
 * 求和会重复计算）。名字里的 `{` / `}` 会破坏 rich 语法，先剔除。
 */
export function formatNodeLabel(
  params: { name: string; value?: number },
  displayMode: "amount" | "percent" | "hidden",
  totalValue: number
): string {
  const name = params.name.replace(/[{}]/g, "");
  const val = params.value ?? 0;
  let suffix = "";
  if (displayMode === "percent") {
    suffix =
      totalValue > 0 ? ((val / totalValue) * 100).toFixed(1) + "%" : "0%";
  } else if (displayMode === "amount") {
    const amount =
      val >= 10000 ? (val / 10000).toFixed(1) + "万" : val.toLocaleString();
    suffix = `¥${amount}`;
  }
  return suffix ? `{name|${name}}  {val|${suffix}}` : `{name|${name}}`;
}
