/**
 * 路由 rank 守卫（#2152 回归网）：
 *
 * 1. **同一父级内声明的 meta.rank 不得重复**——排序键相等时菜单次序只能靠数组
 *    先后兜底，改数组顺序就会跳位置（#2152 的机械成因）；
 * 2. **asset 模块段隔离**：/asset 直接子级占 100~199、「投资管理」孙级占 200~299
 *    （见 asset.ts 的 GRANDCHILD_RANK_BASE），两段不得相交、asset 全树 rank 唯一；
 * 3. **侧边栏可见序**钉住产品决策：品类 → 组合/策略 → 分析 → 对账，
 *    智能分析与对账工作台相邻成组（#2152 验收第 2 条）。
 *
 * 边界：只检查**声明了** rank 的节点；rank 缺失时 router/utils.ts 的 ascending
 * 按数组序兜底补值，属既有框架行为，不在本守卫范围。
 *
 * ⚠️ 本文件必须住在 `src/router/__tests__/`，**不得**放回 `src/router/modules/` 下：
 * router/index.ts 的 import.meta.glob 急加载 modules 目录下全部 ts 文件，
 * 会把 modules 下的 spec 当路由模块在浏览器里执行，vitest 的 suite() 在应用
 * 运行期抛错 → 整个 app 启动即白屏（#2152 本地实测踩坑）。
 * 防线：router/index.ts 的 glob 已加 `!` 开头的 __tests__ / spec / test 负向模式。
 */
import { describe, it, expect } from "vitest";
import home from "../modules/home";
import asset from "../modules/asset";
import agent from "../modules/agent";
import product from "../modules/product";
import errorRoutes from "../modules/error";
import remaining from "../modules/remaining";

type RouteNode = {
  path?: string;
  name?: string;
  meta?: {
    title?: string;
    rank?: number;
    showLink?: boolean;
    hidden?: boolean;
  };
  children?: RouteNode[];
};

const asArray = (mod: unknown): RouteNode[] =>
  (Array.isArray(mod) ? mod : [mod]) as RouteNode[];

/** 全部静态路由模块的顶层条目——与 router/index.ts 的 routes.flat(Infinity) 同构 */
const topLevelRoutes: RouteNode[] = [
  ...asArray(home),
  ...asArray(asset),
  ...asArray(agent),
  ...asArray(product),
  ...asArray(errorRoutes),
  ...asArray(remaining)
];

const labelOf = (n: RouteNode) =>
  n.meta?.title || n.name || n.path || "(未命名)";

/** 收集「同一父级内声明 rank 重复」的问题（递归每个 children 数组） */
function collectSiblingDups(
  siblings: RouteNode[],
  parentLabel: string,
  out: string[]
): void {
  const byRank = new Map<number, string[]>();
  for (const n of siblings) {
    const r = n.meta?.rank;
    if (typeof r !== "number") continue;
    const names = byRank.get(r) ?? [];
    names.push(labelOf(n));
    byRank.set(r, names);
  }
  for (const [rank, names] of byRank) {
    if (names.length > 1) {
      out.push(`${parentLabel} 下 rank=${rank} 重复：${names.join("、")}`);
    }
  }
  for (const n of siblings) {
    if (n.children?.length) {
      collectSiblingDups(n.children, labelOf(n), out);
    }
  }
}

describe("路由 rank 守卫（#2152）", () => {
  it("同一父级内声明的 rank 不得重复（全静态路由模块）", () => {
    const problems: string[] = [];
    collectSiblingDups(topLevelRoutes, "根", problems);
    expect(problems).toEqual([]);
  });

  it("asset 段隔离：直接子级 ∈[100,199]、投资管理孙级 ∈[200,299]，全树 rank 唯一", () => {
    const root = asset as RouteNode;
    const investment = root.children?.find(c => c.name === "InvestmentManage");
    expect(investment, "InvestmentManage 路由应在 asset 模块内").toBeTruthy();

    // 段隔离：两组排序键永不相等（#2152 的根因）
    for (const c of root.children ?? []) {
      const r = c.meta?.rank;
      expect(typeof r).toBe("number");
      expect(
        r,
        `${labelOf(c)} 应落在直接子级段 100~199`
      ).toBeGreaterThanOrEqual(100);
      expect(r, `${labelOf(c)} 应落在直接子级段 100~199`).toBeLessThan(200);
    }
    for (const g of investment?.children ?? []) {
      const r = g.meta?.rank;
      expect(typeof r).toBe("number");
      expect(r, `${labelOf(g)} 应落在孙级段 200~299`).toBeGreaterThanOrEqual(
        200
      );
      expect(r, `${labelOf(g)} 应落在孙级段 200~299`).toBeLessThan(300);
    }

    // 全树唯一：跨层撞键（103 贵金属≡103 账户管理一类）也一并杜绝
    const seen = new Map<number, string>();
    const dups: string[] = [];
    const visit = (n: RouteNode) => {
      const r = n.meta?.rank;
      if (typeof r === "number" && n !== root) {
        if (seen.has(r))
          dups.push(`${seen.get(r)} ≡ ${labelOf(n)}（rank=${r}）`);
        else seen.set(r, labelOf(n));
      }
      n.children?.forEach(visit);
    };
    visit(root);
    expect(dups).toEqual([]);
  });

  it("侧边栏可见序：品类 → 组合/策略 → 分析 → 对账（#2152 验收）", () => {
    /** 深拷贝但保留函数引用（component 是 () => import(...)） */
    const cloneRoute = (n: RouteNode): RouteNode => ({
      ...n,
      meta: { ...n.meta },
      children: n.children?.map(cloneRoute)
    });
    /** 复刻 router/utils.ts ascending：同层按 rank 升序（缺失按 0） */
    const ascending = (arr: RouteNode[]): RouteNode[] => {
      arr.forEach(v => {
        if (v.children?.length) ascending(v.children);
        if (typeof v.meta?.rank !== "number") {
          v.meta = { ...v.meta, rank: 0 };
        }
      });
      return arr.sort((a, b) => (a.meta?.rank ?? 0) - (b.meta?.rank ?? 0));
    };
    /** 复刻 filterTree：showLink:false/hidden:true 且无可见子项 → 移除 */
    const filterTree = (data: RouteNode[]): RouteNode[] => {
      const t = data.map(v => ({ ...v }));
      t.forEach(v => {
        if (v.children) v.children = filterTree(v.children);
      });
      return t.filter(
        v =>
          (v.meta?.showLink !== false && !v.meta?.hidden) ||
          (v.children && v.children.length !== 0)
      );
    };

    const [root] = filterTree(ascending([cloneRoute(asset as RouteNode)]));
    const visibleTitles = (n: RouteNode) =>
      (n.children ?? []).map(c => labelOf(c));

    // /asset 层：聚类顺序 + 分析/对账相邻成组（验收第 2 条）
    expect(visibleTitles(root)).toEqual([
      "特别关注",
      "投资管理",
      "账户管理",
      "策略分析",
      "投资组合",
      "智能分析",
      "对账工作台"
    ]);

    // 投资管理层：只剩品类页（智能分析/对账工作台已移出）
    const investment = root.children?.find(c => c.name === "InvestmentManage");
    expect(visibleTitles(investment as RouteNode)).toEqual(["贵金属", "房产"]);
  });
});
