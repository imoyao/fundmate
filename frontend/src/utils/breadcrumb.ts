// frontend/src/utils/breadcrumb.ts
/**
 * 面包屑路径解析（与侧边栏菜单树同源）。
 *
 * ## 为什么不再用 `route.matched`
 *
 * 静态路由经 `formatTwoStageRoutes` 拍平后，**所有页面都挂到根 `/`（Home）下**，
 * 于是 `route.matched` 恒为 `[Home, 页面]`，面包屑永远渲染成「总览 / 某页」——
 * 哪怕这个页面在侧边栏里属于「资产管理 → 品类持仓」。
 *
 * 这是有证据的（2026-10-29 实机走查，见下方用例）：点侧边栏「同类优选」，
 * 面包屑输出 `总览 / 同类优选`；点「账户管理」输出 `总览 / 账户管理`。
 * 用户因此觉得「面包屑和侧边栏对不上」，切换页面时还会因过渡动画出现空档。
 *
 * ## 取值规则（逐级降级，任何一级都不返回空数组给上层）
 *
 * 1. **精确命中**：菜单树里存在 `path === 当前路径` 的节点 → 取其从根到自身的链；
 * 2. **最长前缀**：详情页（`/asset/ledgers/123`）不在菜单里，取**最长**前缀节点
 *    （`/asset/ledgers`）的链，再由调用方追加当前页标题；
 * 3. 都没有 → 返回 `[]`，调用方退回 `route.matched` 过滤。
 *
 * 取到链后还要做一次**拍平**：侧边栏会被 `hasOneShowingChild` 拍平的目录
 * （只有一个可见子项）不作为一级出现，详见 `isFlattenedDir`。
 * 层级必须与用户看到的侧边栏一致，不能各说各话。
 *
 * ## 为什么这一层是纯函数
 *
 * vitest 的 `environment` 是 `node`（无 DOM），组件挂载测不了；把「树里找路径」
 * 抽成纯函数才能被断言拦住。菜单层级本身是产品决策，改路由结构时这里必须有测试
 * 跟着红，否则面包屑会静默退回「总览 / 某页」而没人发现。
 */

export interface BreadcrumbNode {
  path?: string | null;
  name?: string | null;
  redirect?: unknown;
  meta?: {
    title?: string;
    showLink?: boolean;
    hidden?: boolean;
    [key: string]: unknown;
  } | null;
  children?: BreadcrumbNode[] | null;
}

export interface BreadcrumbCrumb {
  /** 展示文字 */
  title: string;
  /** 点击目标；`null` = 不可点击（末端或无可达子项） */
  to: string | null;
  /** vue-router 列表 key，取路径链拼接，避免同名节点撞 key */
  key: string;
}

/** 节点自身是否会在侧边栏里显示（供「跳过纯隐藏节点」用） */
function isVisible(node: BreadcrumbNode): boolean {
  return node.meta?.showLink !== false && !node.meta?.hidden;
}

/**
 * 该目录在侧边栏里是否**会被拍平**——即它根本不会作为一个菜单层出现。
 *
 * 判据与 `SidebarItem.hasOneShowingChild` 逐字对齐：只有 1 个可见子项、
 * 且该子项没有 `meta.showParent` 时，侧边栏直接渲染子项，目录层消失。
 *
 * 为什么面包屑必须跟着折叠：面包屑是「我在哪」的位置指示，其层级要与用户
 * **看到的**一致。若菜单已把目录层拍平、面包屑却仍渲染它，就出现「侧边栏 1 级 /
 * 面包屑 2 级」——2026-10-30 曾反过来给菜单强加 `showParent` 来凑齐两级，
 * 属于因果倒置（只有一个页面的模块凭空多一层，多一次点击零信息增益）。
 */
function isFlattenedDir(node: BreadcrumbNode): boolean {
  const kids = (node.children ?? []).filter(isVisible);
  return kids.length === 1 && !kids[0].meta?.showParent;
}

/**
 * 取一个目录节点的**第一个可见后代**的路径。
 *
 * 面包屑中间项点击后不该落到空页面：目录路由（如 `/asset`）本身没有组件，
 * 直接 push 会命中 404 或空白。指向它展开后的第一页，与侧边栏点击目录的行为一致。
 */
function firstReachablePath(node: BreadcrumbNode): string | null {
  if (!node.children?.length) return node.path ?? null;
  for (const child of node.children) {
    if (!isVisible(child) && !child.children?.length) continue;
    const found = firstReachablePath(child);
    if (found) return found;
  }
  return node.path ?? null;
}

/** 在菜单树里找一条链：精确命中优先，其次最长前缀 */
function findTrail(
  nodes: BreadcrumbNode[],
  target: string
): { trail: BreadcrumbNode[]; exact: boolean } | null {
  let bestPrefix: BreadcrumbNode[] | null = null;

  const walk = (siblings: BreadcrumbNode[], acc: BreadcrumbNode[]): boolean => {
    for (const node of siblings) {
      const path = node.path ?? "";
      const next = [...acc, node];

      if (path && path === target) {
        bestPrefix = next;
        return true;
      }

      // 前缀候选：`/a/b/123` 命中 `/a/b`，但不允许 `/a/bc` 误命中 `/a/b`
      if (path && path !== "/" && target.startsWith(`${path}/`)) {
        if (!bestPrefix || next.length > bestPrefix.length) bestPrefix = next;
      }

      if (node.children?.length && walk(node.children, next)) return true;
    }
    return false;
  };

  walk(nodes, []);
  if (!bestPrefix) return null;

  const trail = bestPrefix as BreadcrumbNode[];
  const last = trail[trail.length - 1];
  return { trail, exact: (last.path ?? "") === target };
}

function toCrumbs(trail: BreadcrumbNode[]): BreadcrumbCrumb[] {
  const crumbs: BreadcrumbCrumb[] = [];
  const keys: string[] = [];

  trail.forEach((node, index) => {
    const title = node.meta?.title;
    if (!title) return;
    // 纯隐藏节点（如 `hidden: true` 的详情页父级）不进面包屑
    if (!isVisible(node) && !node.children?.length) return;
    // 侧边栏已拍平的目录（单可见子项）不作为一级出现，否则层级对不上。
    // 末项不折叠：它本身就是当前页，折叠掉会把面包屑变成空的。
    const isLast = index === trail.length - 1;
    if (!isLast && isFlattenedDir(node)) return;

    const path = node.path ?? "";
    keys.push(path || `#${index}`);
    crumbs.push({
      title,
      // 末端由调用方决定是否可点（当前页通常不可点）
      to: isLast ? null : firstReachablePath(node),
      key: keys.join(" > ")
    });
  });

  return crumbs;
}

/**
 * 主入口：把菜单树 + 当前路径解析成面包屑。
 *
 * @param menus 侧边栏菜单树（`permissionStore.wholeMenus`，保留原始层级）
 * @param currentPath 当前路由 path
 * @param currentTitle 当前页标题，用于「前缀命中」时补末项
 */
export function buildBreadcrumb(
  menus: BreadcrumbNode[] | undefined,
  currentPath: string,
  currentTitle?: string
): BreadcrumbCrumb[] {
  if (!menus?.length || !currentPath) return [];

  const found = findTrail(menus, currentPath);
  if (!found) return [];

  const crumbs = toCrumbs(found.trail);

  if (!found.exact) {
    // 详情页一类：菜单里只有它的上级，补上当前页自身（不可点击）
    const last = found.trail[found.trail.length - 1];
    const lastTitle = last?.meta?.title;
    const ownTitle = currentTitle || "";
    if (ownTitle && ownTitle !== lastTitle) {
      crumbs.push({
        title: ownTitle,
        to: null,
        key: `${crumbs[crumbs.length - 1]?.key ?? ""} > ${currentPath}`
      });
    }
  }

  return crumbs;
}
