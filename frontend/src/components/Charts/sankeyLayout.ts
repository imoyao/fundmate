/**
 * 桑基图的几何布局与取色（#980 批 B8 从 `Charts/SankeyChart.vue` 抽出）。
 *
 * 抽出的理由：这个组件里真正「难」的部分是**手算布局** —— 分层 BFS、资产负债分支配色、
 * 同层排序权重、分支间 60px 额外间隔。原来它和「什么时候 init / dispose」混在一个文件里，
 * 而那部分（生命周期）已由 `useEchartsLifecycle` 接管。把几何算法单独拿出来后，
 * 它是纯函数，可以脱离 ECharts 与浏览器量测直接单测。
 *
 * 取色通过 `readVar` 注入而不是直接 import `getCssVar`：后者要读
 * `getComputedStyle(document.documentElement)`，在 jsdom 里恒为空串，单测会全部
 * 退化成 fallback 分支，等于没测到映射表。注入之后，单测可以给一个假 reader。
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
 * 注意这里**不是**资产类别令牌的唯一来源：`股票/基金/ETF/可转债/虚拟货币/银行存款`
 * 用的是 `--asset-cat-*`，与全站资产分类色保持一致；但「总资产 / 净资产 / 流动资金 /
 * 投资理财」这些是这张图自己的层级节点，没有对应的资产类别，故用品牌色与调色板。
 */
export const NODE_COLOR_VARS: Record<string, string> = {
  总资产: "--brand-700",
  净资产: "--color-fall",
  总负债: "--color-neutral",
  流动资金: "--palette-mint-green",
  投资理财: "--palette-periwinkle",
  固定资产: "--palette-warm-taupe",
  应收款: "--palette-stone-gray",
  保险项目: "--color-accent",
  活钱: "--palette-muted-blue",
  稳健底仓: "--palette-thistle",
  长期增值: "--brand-700",
  高风险博弈: "--sankey-speculative",
  保险保障: "--color-accent",
  未配置资产: "--color-neutral",
  股票: "--asset-cat-stock",
  基金: "--asset-cat-fund",
  可转债: "--asset-cat-bond",
  ETF: "--asset-cat-etf",
  虚拟货币: "--asset-cat-crypto",
  银行存款: "--asset-cat-saving"
};

/** 负债类节点名的兜底正则（映射表里没有的负债子项走 neutral） */
const LIABILITY_NAME_RE = /贷|借|信用卡|负债/;

/**
 * 节点颜色：先查映射表，再按负债语义兜底，最后退到三级文字色。
 *
 * 为什么负债要有兜底：负债子项的名字是用户自己的（「房贷」「借家人的钱」），
 * 后端可以新增而前端不知道。漏了兜底这些节点会变成透明/默认蓝，在一屏资产色里
 * 反而最刺眼 —— 语义正好反了。
 */
export function getNodeColor(name: string, readVar: VarReader): string {
  const varName = NODE_COLOR_VARS[name];
  if (varName) {
    const color = readVar(varName);
    if (color) return color;
  }
  if (LIABILITY_NAME_RE.test(name)) {
    return readVar("--color-neutral") || "var(--text-tertiary)";
  }
  return readVar("--text-tertiary");
}

/**
 * 最大层级（供 `computeManualLayout` 算列宽用）。
 *
 * ⚠️ 这段 BFS 与 `computeManualLayout` 内部那段**看起来重复**，但两者对「环」的处理
 * 不同：这里把未访问节点留在 `-1`，`Math.max(..., 0)` 兜底；那边用 `undefined` 判定、
 * 未触达的节点不会进入布局。本批只搬运不合并，保留原样以免改动有环数据下的列宽。
 */
export function computeMaxLevel(
  nodes: SankeyDataNode[],
  links: SankeyLink[]
): number {
  const levels: Record<string, number> = {};
  const queue: string[] = [];
  nodes.forEach(n => {
    levels[n.name] = -1;
  });
  nodes.forEach(n => {
    const hasSource = links.some(l => l.target === n.name);
    if (!hasSource) {
      levels[n.name] = 0;
      queue.push(n.name);
    }
  });
  if (queue.length === 0 && nodes.length > 0) {
    levels[nodes[0].name] = 0;
    queue.push(nodes[0].name);
  }
  let head = 0;
  while (head < queue.length) {
    const curr = queue[head++];
    links.forEach(l => {
      if (l.source === curr && levels[l.target] === -1) {
        levels[l.target] = levels[curr] + 1;
        queue.push(l.target);
      }
    });
  }
  return Math.max(...Object.values(levels), 0);
}

/** 同层内的排序权重：让「投资理财 / 固定资产 / 流动资金」这类主分支从上到下稳定 */
const ORDER_WEIGHT: Record<string, number> = {
  投资理财: 0,
  固定资产: 1,
  流动资金: 2,
  总资产: 0,
  净资产: 0,
  总负债: 1,
  长期增值: 0,
  股票: 0,
  未配置资产: 1,
  房贷: 2,
  借家人的钱: 3
};

/** 单节点高度 / 同分支内节点间距 / 资产与负债两支之间的额外间隔 */
const NODE_HEIGHT = 20;
const NODE_GAP = 10;
const BRANCH_GAP = 60;
/** 每一列第一个节点的起始 y */
const TOP_PAD = 20;

/**
 * 手算布局：分层 → 按资产负债分两支 → 同层排序 → 依次堆叠。
 *
 * 为什么不用 ECharts 的自动布局（`layout: 'none'` 之外的默认）：自动布局把节点按
 * 流量居中，资产与负债两支会混在一起，「总资产 → 净资产 / 总负债」这层语义就没了。
 * 手算的代价是每次宽度变化都要重跑，所以调用方用 `reuse: true` 复用实例而不是重建。
 */
export function computeManualLayout(
  nodes: SankeyDataNode[],
  links: SankeyLink[],
  chartWidth: number,
  levelCount: number,
  leftPad: number,
  rightPad: number,
  readVar: VarReader
): { nodes: Record<string, unknown>[]; maxY: number } {
  const outAdj: Record<string, string[]> = {};
  const inAdj: Record<string, string[]> = {};
  nodes.forEach(n => {
    outAdj[n.name] = [];
    inAdj[n.name] = [];
  });
  links.forEach(l => {
    outAdj[l.source].push(l.target);
    inAdj[l.target].push(l.source);
  });

  const nodeLevel: Record<string, number> = {};
  const queue: string[] = [];
  nodes.forEach(n => {
    if (inAdj[n.name].length === 0) {
      nodeLevel[n.name] = 0;
      queue.push(n.name);
    }
  });
  if (queue.length === 0 && nodes.length > 0) {
    nodeLevel[nodes[0].name] = 0;
    queue.push(nodes[0].name);
  }
  let head = 0;
  while (head < queue.length) {
    const curr = queue[head++];
    (outAdj[curr] || []).forEach(next => {
      if (nodeLevel[next] === undefined) {
        nodeLevel[next] = nodeLevel[curr] + 1;
        queue.push(next);
      }
    });
  }

  const branchMap: Record<string, "asset" | "liability"> = {};
  function markLiability(name: string) {
    if (branchMap[name] === "liability") return;
    branchMap[name] = "liability";
    (outAdj[name] || []).forEach(child => markLiability(child));
  }
  if (nodeLevel["总负债"] !== undefined) markLiability("总负债");
  nodes.forEach(n => {
    if (!branchMap[n.name]) branchMap[n.name] = "asset";
  });

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

  const drawWidth = chartWidth - leftPad - rightPad;
  const colWidth = levelCount > 1 ? drawWidth / (levelCount - 1) : drawWidth;

  const levelGroups = Object.entries(nodeLevel).reduce(
    (acc, [name, lvl]) => {
      if (!acc[lvl]) acc[lvl] = [];
      acc[lvl].push(name);
      return acc;
    },
    {} as Record<number, string[]>
  );

  const layouted: Record<string, unknown>[] = [];
  let globalMaxY = 0;

  Object.entries(levelGroups).forEach(([lvlStr, names]) => {
    const lvl = parseInt(lvlStr);
    const x = leftPad + lvl * colWidth;

    const assetNames = names.filter(n => branchMap[n] === "asset");
    const liabilityNames = names.filter(n => branchMap[n] === "liability");

    assetNames.sort(
      (a, b) => (ORDER_WEIGHT[a] ?? 999) - (ORDER_WEIGHT[b] ?? 999)
    );
    liabilityNames.sort(
      (a, b) => (ORDER_WEIGHT[a] ?? 999) - (ORDER_WEIGHT[b] ?? 999)
    );

    let yCursor = TOP_PAD;

    assetNames.forEach(name => {
      const rawNode = nodes.find(n => n.name === name)!;
      layouted.push({
        ...rawNode,
        name,
        x,
        y: yCursor,
        value: nodeFlow[name] || 0,
        itemStyle: { color: getNodeColor(name, readVar) },
        label: {
          position: lvl === 0 ? "left" : "right",
          distance: 6
        }
      });
      yCursor += NODE_HEIGHT + NODE_GAP;
    });

    if (liabilityNames.length > 0) {
      yCursor += BRANCH_GAP - NODE_GAP;
    }
    liabilityNames.forEach(name => {
      const rawNode = nodes.find(n => n.name === name)!;
      layouted.push({
        ...rawNode,
        name,
        x,
        y: yCursor,
        value: nodeFlow[name] || 0,
        itemStyle: { color: getNodeColor(name, readVar) },
        label: {
          position: "right",
          distance: 6
        }
      });
      yCursor += NODE_HEIGHT + NODE_GAP;
    });

    globalMaxY = Math.max(globalMaxY, yCursor);
  });

  return { nodes: layouted, maxY: globalMaxY };
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
 * 节点标签文案：三种显示模式。
 *
 * `percent` 的百分比以「总资产」节点的值为分母（不是所有节点之和 —— 桑基图里
 * 各层节点是同一笔钱的不同切法，求和会重复计算）。
 */
export function formatNodeLabel(
  params: { name: string; value?: number },
  displayMode: "amount" | "percent" | "hidden",
  totalValue: number
): string {
  const val = params.value ?? 0;
  if (displayMode === "hidden") return params.name;
  if (displayMode === "percent") {
    const pct =
      totalValue > 0 ? ((val / totalValue) * 100).toFixed(1) + "%" : "0%";
    return `${params.name}\n${pct}`;
  }
  const amount =
    val >= 10000 ? (val / 10000).toFixed(1) + "万" : val.toLocaleString();
  return `${params.name}\n¥${amount}`;
}
