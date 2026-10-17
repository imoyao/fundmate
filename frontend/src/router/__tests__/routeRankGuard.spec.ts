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
    // #2150：「智能分析」标题改为「复盘」；且此处 toEqual 恰好钉住了一个隐含契约——
    // 该条目在侧边栏**只出现一次**。#2152 移出「投资管理」时只在新位置加了一份、
    // 旧的那份没删（两份 path/name 全同，filterTree 不按 name 去重），侧边栏因此
    // 渲染出两个同名条目；`toEqual` 是数组全等，多一个就红，所以这条断言一直
    // 有能力咬住它——只是当时没人把它当回事。重复声明已于 #2150 删除。
    expect(visibleTitles(root)).toEqual([
      "特别关注",
      "投资管理",
      "账户管理",
      "策略分析",
      "投资组合",
      "复盘",
      "对账工作台"
    ]);

    // 投资管理层：品类页 + 「同类优选」（复盘/对账工作台已移出）。
    // 本条断言此前停在 ["贵金属","房产"]，而该页（rank 6、showLink:true）
    // 是本目录下的可见子级——它上线时没人同步这行，于是本用例一直红着。
    // 断言按现实补齐：**这是补账不是放宽**，可见项仍被逐个钉住。
    // 2026-10-17：「同类风险榜」更名「同类优选」（口径是持仓∪自选的同类体检，
    // 「榜」字像全市场排行，与实际错位），此断言随现实同步。
    const investment = root.children?.find(c => c.name === "InvestmentManage");
    expect(visibleTitles(investment as RouteNode)).toEqual([
      "贵金属",
      "房产",
      "同类优选"
    ]);
  });

  // #2150：把「同一个 path / name 在 asset 模块里声明两次」机械化拦下——
  // 上一条断言咬得住是因为它刚好列全了可见项；换个人加一条别的重复路由，
  // 只要不在 /asset 直接子级的可见项里，就没人看得见。此条与排序无关，只管重复。
  it("#2150：asset 模块内不得出现重复的 path / name 声明（同名条目会渲染两遍）", () => {
    // ⚠️ `seen` 必须跨**整棵子树**共享，不能每个 children 数组各自一份：
    // #2152 的那份重复正是「父级直接子级一份 + 孙级一份」，各层独立去重看不见它。
    // （首版就是按层去重写的，在带 bug 的 dev 上真跑成绿——探针一测才发现。
    //   判据写好后必须在**真实缺陷样本**上跑一次，别只看绿。）
    const dups: string[] = [];
    const seen = new Map<string, string>();
    const walk = (nodes: RouteNode[]) => {
      for (const n of nodes) {
        for (const key of ["path", "name"] as const) {
          const v = n[key];
          if (!v) continue;
          const k = `${key}:${v}`;
          if (seen.has(k)) {
            dups.push(`重复 ${k}（${seen.get(k)} 与 ${labelOf(n)}）`);
          } else {
            seen.set(k, labelOf(n));
          }
        }
        if (n.children) walk(n.children);
      }
    };
    walk(asArray(asset));
    expect(dups, "同一 path/name 声明两次会让侧边栏渲染出两个条目").toEqual([]);
  });

  it("#2150：判据非空转——把重复声明注回去必须报红", () => {
    // 复现 #2152 留下的那一份：同一个 path/name 在父级与孙级各声明一次。
    const regressed: RouteNode[] = [
      {
        path: "/asset",
        name: "Asset",
        children: [
          {
            path: "investment",
            name: "InvestmentManage",
            children: [{ path: "/analysis", name: "AssetAnalysis" }]
          },
          { path: "/analysis", name: "AssetAnalysis" }
        ]
      }
    ];
    const seen = new Map<string, string>();
    const dups: string[] = [];
    const walk = (nodes: RouteNode[]) => {
      for (const n of nodes) {
        for (const key of ["path", "name"] as const) {
          const v = n[key];
          if (!v) continue;
          const k = `${key}:${v}`;
          if (seen.has(k)) dups.push(k);
          else seen.set(k, labelOf(n));
        }
        if (n.children) walk(n.children);
      }
    };
    walk(regressed);
    expect(
      dups.length,
      "注回重复声明后判据必须命中，否则守门是装饰"
    ).toBeGreaterThan(0);
  });
});
