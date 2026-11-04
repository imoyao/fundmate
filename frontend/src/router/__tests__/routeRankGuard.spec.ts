/**
 * 路由 rank 守卫（#2152 回归网 + 2026-10-29 侧边栏重组）：
 *
 * 1. **同一父级内声明的 meta.rank 不得重复**——排序键相等时菜单次序只能靠数组
 *    先后兜底，改数组顺序就会跳位置（#2152 的机械成因）；
 * 2. **asset 模块段隔离**：/asset 直接子级占 100~199、全部孙级占 200~299，
 *    两段不得相交、asset 全树 rank 唯一；
 * 3. **侧边栏结构钉住产品决策**（2026-10-29 重组）：按财务动作切四个顶级
 *    （资产概览 / 资产管理 / 记账中心 / 账本精灵），资产管理下四个语义分组，
 *    每个分组的可见项逐个钉死。
 * 4. **菜单标题统一 4 字**（用户明确要求）：除资产品类名（「贵金属」「房产」）
 *    这类无法用 4 字准确描述的外，一律 4 个汉字。
 * 5. **单子项目录一律拍平，禁止用 `showParent` 硬撑一层**：只有一页的模块不该有
 *    目录层——`SidebarItem.hasOneShowingChild` 本来就把它拍平，点击直达页面。
 *    面包屑已对「单可见子项目录」同步折叠（`utils/breadcrumb.ts` 的
 *    `isFlattenedDir`），两侧天然一致。2026-10-30 曾为让面包屑有两级而给账本精灵
 *    加 `showParent`，属因果倒置：多一层 = 多一次点击 + 多一个名字。
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
import { buildBreadcrumb } from "@/utils/breadcrumb";
import home from "../modules/home";
import asset from "../modules/asset";
import record from "../modules/record";
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
    showParent?: boolean;
  };
  children?: RouteNode[];
};

const asArray = (mod: unknown): RouteNode[] =>
  (Array.isArray(mod) ? mod : [mod]) as RouteNode[];

/** 全部静态路由模块的顶层条目——与 router/index.ts 的 routes.flat(Infinity) 同构 */
const topLevelRoutes: RouteNode[] = [
  ...asArray(home),
  ...asArray(asset),
  ...asArray(record),
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

/** 复刻 router/utils.ts ascending：同层按 rank 升序 */
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
  const t = data.map(v => ({ ...v, meta: { ...v.meta } }));
  t.forEach(v => {
    if (v.children) v.children = filterTree(v.children);
  });
  return t.filter(
    v =>
      (v.meta?.showLink !== false && !v.meta?.hidden) ||
      (v.children && v.children.length !== 0)
  );
};

const cloneRoute = (n: RouteNode): RouteNode => ({
  ...n,
  meta: { ...n.meta },
  children: n.children?.map(cloneRoute)
});

/** 取某模块侧边栏可见的直接子项标题（已过 ascending + filterTree） */
function visibleTitlesOf(mod: unknown, nodeName?: string): string[] {
  const [root] = filterTree(ascending([cloneRoute(asArray(mod)[0])]));
  const target =
    root.children?.find(c => c.name === nodeName) ?? (root as RouteNode);
  return (target.children ?? []).map(c => labelOf(c));
}

describe("路由 rank 守卫（#2152）", () => {
  it("同一父级内声明的 rank 不得重复（全静态路由模块）", () => {
    const problems: string[] = [];
    collectSiblingDups(topLevelRoutes, "根", problems);
    expect(problems).toEqual([]);
  });

  it("asset 段隔离：直接子级 ∈[100,199]、全部孙级 ∈[200,299]，全树 rank 唯一", () => {
    const root = asset as RouteNode;

    // 直接子级段
    for (const c of root.children ?? []) {
      const r = c.meta?.rank;
      expect(typeof r).toBe("number");
      expect(
        r,
        `${labelOf(c)} 应落在直接子级段 100~199`
      ).toBeGreaterThanOrEqual(100);
      expect(r, `${labelOf(c)} 应落在直接子级段 100~199`).toBeLessThan(200);
    }

    // 孙级段：2026-10-29 起有 4 个分组，不能只查单个目录
    const groups = (root.children ?? []).filter(c => c.children?.length);
    expect(groups.length, "asset 应有 4 个语义分组").toBe(4);
    for (const g of groups) {
      for (const child of g.children ?? []) {
        const r = child.meta?.rank;
        expect(typeof r).toBe("number");
        expect(
          r,
          `${labelOf(g)} / ${labelOf(child)} 应落在孙级段 200~299`
        ).toBeGreaterThanOrEqual(200);
        expect(
          r,
          `${labelOf(g)} / ${labelOf(child)} 应落在孙级段 200~299`
        ).toBeLessThan(300);
      }
    }

    // 全树唯一：跨层撞键（103 贵金属 ≡ 103 账户管理 一类）也一并杜绝
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

  it("侧边栏结构：四个顶级按财务动作切开（2026-10-29 重组）", () => {
    const order = filterTree(ascending(topLevelRoutes.map(cloneRoute)))
      .map(labelOf)
      .filter(t => t !== "产品详情" && !t.startsWith("("));

    // 顶级只剩「看 / 管 / 记 / 助手」四种财务动作。
    // 旧结构是「总览 + 资产管理」两套分组逻辑并存（总览按使用频次、资产管理按
    // 资产类型），同一动作被劈到两个顶级下，这是「没有层次感」的机械成因。
    expect(order).toEqual(["资产概览", "资产管理", "记账中心", "账本精灵"]);
  });

  it("资产管理：四个分组，各自可见项逐个钉住", () => {
    // 2026-10-30 二次修订：分组名要能被直接读懂（用户否掉了「品类持仓 / 观察名单 /
    // 账户家庭」三个硬凑的名词拼接），判断依据是**这一组装的是什么样的页面**。
    expect(visibleTitlesOf(asset)).toEqual([
      "组合策略",
      "实物资产",
      "我的关注",
      "账户成员"
    ]);
    expect(visibleTitlesOf(asset, "AssetPortfolioGroup")).toEqual([
      "投资组合",
      "策略分析",
      "定投计划"
    ]);
    // 只装「要手动登记、手动估值」的线下资产。
    // 「同类优选」曾在此组（旧名「品类持仓」），但它是**基金筛选页**不是持仓，
    // 输入是你的持仓与自选——名字与成员互相否定，故移到「我的关注」。
    expect(visibleTitlesOf(asset, "AssetCategoryGroup")).toEqual([
      "贵金属",
      "房产"
    ]);
    // 三个成员的共同点：还没买、在挑、在盯。「我的自选」原在 home 的「总览」下、
    // 「特别关注」在「资产管理」下，同一件心事隔着两个顶级——归到一起是本轮核心修正。
    expect(visibleTitlesOf(asset, "AssetWatchGroup")).toEqual([
      "我的自选",
      "特别关注",
      "同类优选"
    ]);
    expect(visibleTitlesOf(asset, "AssetHouseholdGroup")).toEqual([
      "账户管理",
      "家庭成员"
    ]);
  });

  it("资产概览与记账中心：可见项逐个钉住", () => {
    // 概览 = 纯读（复盘 / 持仓分析都是"看结果"，不下配置、不录事实）
    expect(visibleTitlesOf(home)).toEqual([
      "投资概览",
      "资产总览",
      "持仓分析",
      "投资复盘"
    ]);
    // 记账 = 录入 → 流水 → 核对，顺序即实际动线
    expect(visibleTitlesOf(record)).toEqual([
      "全面盘点",
      "交易流水",
      "分红股息",
      "对账中心"
    ]);
  });

  it("菜单标题统一 4 字（豁免资产品类名）", () => {
    // 用户明确要求：侧边栏都使用 4 个字，除非无法用 4 个字描述。
    // 豁免项必须是**资产类别名词**——「贵金属」「房产」扩成四个字（如「实物房产」）
    // 会改变语义或与页面标题脱节，属"无法用 4 字描述"。
    const EXEMPT = new Set(["贵金属", "房产"]);
    const offenders: string[] = [];

    const walk = (nodes: RouteNode[], visible: boolean) => {
      for (const n of nodes) {
        const isVisible =
          visible && n.meta?.showLink !== false && !n.meta?.hidden;
        const title = n.meta?.title;
        if (isVisible && title && !EXEMPT.has(title)) {
          if ([...title].length !== 4) {
            offenders.push(`${title}（${[...title].length} 字，${n.path}）`);
          }
        }
        if (n.children?.length) walk(n.children, isVisible);
      }
    };
    walk(topLevelRoutes, true);
    expect(offenders).toEqual([]);
  });

  it("单子项目录一律拍平：账本精灵在侧边栏只有 1 级，不许靠 showParent 撑层级", () => {
    // 判据一：全静态路由里**不得**出现 `showParent`。它唯一的用途是把单子项目录
    // 强行渲染成可折叠分组——而这正是「一个页面的模块凭空多一层」的来源。
    const offenders: string[] = [];
    const walk = (nodes: RouteNode[] | undefined): void => {
      for (const n of nodes ?? []) {
        if (n.meta?.showParent) offenders.push(labelOf(n));
        walk(n.children);
      }
    };
    walk(topLevelRoutes);
    expect(
      offenders,
      "showParent 把单子项目录撑成一层，而面包屑已折叠 → 两侧层级打架"
    ).toEqual([]);

    // 判据二：账本精灵的侧边栏形态 = 顶层只有一个「账本精灵」，点击直达 /agent/chat。
    // 路由仍是两级（Layout 容器 + 页面），但**菜单深度为 1**。
    const [agentRoot] = filterTree(ascending([cloneRoute(asArray(agent)[0])]));
    expect(labelOf(agentRoot)).toBe("账本精灵");
    expect(agentRoot.meta?.showLink).toBe(false);
    const visibleKids = (agentRoot.children ?? []).filter(
      c => c.meta?.showLink !== false && !c.meta?.hidden
    );
    expect(visibleKids.map(labelOf)).toEqual(["账本精灵"]);
    expect(visibleKids[0].path).toBe("/agent/chat");
  });

  it("判据非空转：把 showParent 注回去必须报红", () => {
    const regressed = cloneRoute(asArray(agent)[0]);
    regressed.children[0].meta.showParent = true;
    const offenders: string[] = [];
    const walk = (nodes: RouteNode[] | undefined): void => {
      for (const n of nodes ?? []) {
        if (n.meta?.showParent) offenders.push(labelOf(n));
        walk(n.children);
      }
    };
    walk([regressed]);
    expect(offenders, "注回 showParent 后判据必须命中").toEqual(["账本精灵"]);
  });

  // #2150：把「同一个 path / name 在 asset 模块里声明两次」机械化拦下。
  // 上一条断言咬得住是因为它刚好列全了可见项；换个人加一条别的重复路由，
  // 只要不在 /asset 直接子级的可见项里，就没人看得见。此条与排序无关，只管重复。
  it("#2150：asset 模块内不得出现重复的 path / name 声明（同名条目会渲染两遍）", () => {
    // ⚠️ `seen` 必须跨**整棵子树**共享，不能每个 children 数组各自一份：
    // #2152 的那份重复正是「父级直接子级一份 + 孙级一份」，各层独立去重看不见它。
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

  it("面包屑：每个可达页面的末项必须是页面自己的标题（含隐藏页与下钻页）", () => {
    // 2026-10-30 实机盘查（Edge，27 个页面）：面包屑把 showLink:false 的页面整段
    // 丢弃后，末项要么消失、要么塌回 `route.matched` 的首级「资产概览」。
    // 判据：任何**绝对路径**的可达页面，面包屑末项 === 该页面 meta.title。
    const tree = ascending(topLevelRoutes.map(cloneRoute));
    const offenders: string[] = [];

    const visit = (nodes: RouteNode[]) => {
      for (const n of nodes) {
        const p = n.path ?? "";
        const title = n.meta?.title;
        // 跳过容器（相对 path）与带参路由（单独用 `/fund/004369` 那条用例覆盖）
        if (p.startsWith("/") && p !== "/" && !p.includes(":") && title) {
          const crumbs = buildBreadcrumb(tree as any, p, title);
          const last = crumbs[crumbs.length - 1];
          if (!last) offenders.push(`${p} → 面包屑为空`);
          else if (last.title !== title) {
            offenders.push(
              `${p} → 末项「${last.title}」≠ 页面标题「${title}」`
            );
          }
        }
        if (n.children?.length) visit(n.children);
      }
    };
    visit(tree);
    expect(offenders).toEqual([]);
  });

  it("面包屑：隐藏页/下钻页不得塌回「资产概览 / 某页」（实机盘查回归）", () => {
    const tree = ascending(topLevelRoutes.map(cloneRoute));
    const chain = (p: string, title?: string) =>
      buildBreadcrumb(tree as any, p, title).map(c => c.title);

    // 这些页面 showLink:false 或 hidden，不在侧边栏，但用户能直达：
    // 它们的父级必须来自路由结构（资产管理 / 记账中心），不是路径前缀猜的。
    expect(chain("/stocks")).toEqual(["资产管理", "股票"]);
    expect(chain("/funds")).toEqual(["资产管理", "基金"]);
    expect(chain("/investment/holding-import")).toEqual([
      "记账中心",
      "导入持仓"
    ]);
    expect(chain("/investment/manual")).toEqual(["记账中心", "手动记账"]);
    expect(chain("/investment/reconcile")).toEqual(["记账中心", "E账户对账"]);
    // 反例：它的 path 以 /asset 开头，但结构上归「记账中心」——前缀法会答错
    expect(chain("/asset/asset-entry")).toEqual(["记账中心", "录入资产"]);
    // 带参路由（/fund/004369 → /:assetType/:symbol）：单级，不虚构父级
    expect(chain("/fund/004369", "产品详情")).toEqual(["产品详情"]);
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
            name: "AssetCategoryGroup",
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
