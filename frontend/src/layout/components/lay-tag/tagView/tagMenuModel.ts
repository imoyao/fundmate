/**
 * 标签栏右键/下拉菜单的状态机（#980 拆分自 layout/components/lay-tag/index.vue）。
 *
 * 原实现 `showMenuModel` 是一段「按当前标签位置推导每个菜单项能不能点」的分支瀑布，
 * 但它混在组件里、直接改 `tagsViews` 的响应式对象，**没法单独断言**——于是这页
 * 每次改动都只能靠手点右键菜单验。这里把判断抽成纯函数：
 *
 * - 输入：当前 5 个「关闭类」菜单项的 show/disabled 快照 + 标签总数 + 当前下标 + 相邻标签是否固定；
 * - 输出：新的快照。
 *
 * 纯函数只负责**算出应该是什么状态**，把状态写回 `tagsViews` 的动作留在 `useTagMenu`。
 * 这样「下标为 1 时关闭左侧要藏起来」这类规则就可以逐条钉住。
 */

import { isAllEmpty, isEqual } from "@pureadmin/utils";

/** 菜单项在 `tagsViews` 里的下标（与 hooks/useTag.ts 的初始化顺序一一对应） */
export const MENU_INDEX = {
  refresh: 0,
  closeCurrent: 1,
  closeLeft: 2,
  closeRight: 3,
  closeOther: 4,
  closeAll: 5,
  fullscreen: 6
} as const;

/** 右键菜单的最小宽度（px）：贴着右边缘右键时要往回挪这么多 */
export const MENU_MIN_WIDTH = 140;

/** 一个菜单项的可变状态（`icon` / `text` / `divided` 不随右键位置变化，不进本结构） */
export interface MenuState {
  show: boolean;
  disabled: boolean;
}

/** 「关闭类」菜单项在 `tagsViews` 里的下标集合：关闭当前 / 左侧 / 右侧 / 其他 / 全部 */
export const MENU_BODY_INDEXES = [1, 2, 3, 4, 5] as const;

/** 从 `tagsViews` 摘出关闭类菜单项的状态快照（不持有响应式引用） */
export function snapshotMenuBody(
  tagsViews: ReadonlyArray<MenuState>
): MenuState[] {
  return MENU_BODY_INDEXES.map(i => ({
    show: tagsViews[i].show,
    disabled: tagsViews[i].disabled
  }));
}

/** 把快照写回 `tagsViews` 的关闭类菜单项（就地改，保持与原有响应式行为一致） */
export function applyMenuBody(
  tagsViews: MenuState[],
  states: ReadonlyArray<MenuState>
): void {
  MENU_BODY_INDEXES.forEach((target, i) => {
    tagsViews[target].show = states[i].show;
    tagsViews[target].disabled = states[i].disabled;
  });
}

/**
 * 找出当前右键/激活标签在 `multiTags` 里的下标。
 *
 * 优先级与原实现一致：**params → query → path**。带动态参数的路由（如组合详情
 * `/asset/portfolio/123`）只能靠 params 区分，同路径不同 query 的标签只能靠 query 区分。
 */
export function resolveMenuIndex(
  multiTags: ReadonlyArray<any>,
  target: { path: string; query?: object; params?: object }
): number {
  const { path, query = {}, params = {} } = target;
  if (!isAllEmpty(params))
    return multiTags.findIndex(v => isEqual(v.params, params));
  if (!isAllEmpty(query))
    return multiTags.findIndex(v => isEqual(v.query, query));
  return multiTags.findIndex(v => v.path === path);
}

export interface MenuModelInput {
  /** 关闭类菜单项（tagsViews[1..5]）的当前状态 */
  current: ReadonlyArray<MenuState>;
  /** 标签总数 */
  routeLength: number;
  /** 当前标签下标；-1 表示没找到 */
  currentIndex: number;
  /** 当前标签是否带 `meta.fixedTag`（固定标签不允许关闭） */
  currentIsFixedTag: boolean;
  /** 当前标签左侧那个标签是否固定（固定时「关闭左侧」无意义） */
  prevIsFixedTag: boolean;
  /** 当前路径是否是「首页重定向路径」（`/redirect${topPath}`），这条也按顶级菜单处理 */
  currentPathIsTopRedirect: boolean;
}

/**
 * 推导关闭类菜单项的新状态。
 *
 * 五条分支与原实现逐条对齐（顺序不能换：先判「左侧是顶级菜单」，再判「当前是最后一个」）：
 *
 * 1. 左侧是顶级菜单、右侧还有别的标签 → 藏「关闭左侧」；
 * 2. 左侧是顶级菜单、总共只有两个标签 → 藏「关闭左侧/右侧/其他」；
 * 3. 当前是最后一个标签 → 藏「关闭右侧」；左侧若固定，再藏「关闭左侧」；
 * 4. 当前是第一个标签，或当前是首页重定向路径 → 关闭类全部禁用；
 * 5. 兜底：全部可用，但左侧固定时藏「关闭左侧」。
 *
 * 每条分支末尾都要过一遍 `fixedTagDisabled`：当前标签是固定标签时，关闭类一律禁用。
 */
export function resolveMenuModel(input: MenuModelInput): MenuState[] {
  const {
    routeLength,
    currentIndex,
    currentIsFixedTag,
    prevIsFixedTag,
    currentPathIsTopRedirect
  } = input;

  const items = input.current.map(s => ({
    show: s.show,
    disabled: s.disabled
  }));
  /** tagsViews[1..5] → items[0..4] */
  const showMenus = (value: boolean) => items.forEach(i => (i.show = value));
  const disabledMenus = (value: boolean, fixedTag = false) => {
    items.forEach(i => (i.disabled = value));
    if (fixedTag) {
      // 「关闭左侧」（tagsViews[2]）
      items[1].show = false;
      items[1].disabled = true;
    }
  };
  const fixedTagDisabled = () => {
    if (currentIsFixedTag) items.forEach(i => (i.disabled = true));
  };

  showMenus(true);

  if (currentIndex === 1 && routeLength !== 2) {
    // 左侧是顶级菜单，右侧还有别的标签
    items[1].show = false;
    [0, 2, 3, 4].forEach(i => (items[i].disabled = false));
    items[1].disabled = true;
    fixedTagDisabled();
  } else if (currentIndex === 1 && routeLength === 2) {
    disabledMenus(false);
    // 左侧是顶级菜单，右侧没有别的标签
    [1, 2, 3].forEach(i => {
      items[i].show = false;
      items[i].disabled = true;
    });
    fixedTagDisabled();
  } else if (routeLength - 1 === currentIndex && currentIndex !== 0) {
    // 当前是最后一个标签：右侧没有东西可关
    items[2].show = false;
    [0, 1, 3, 4].forEach(i => (items[i].disabled = false));
    items[2].disabled = true;
    if (prevIsFixedTag) {
      items[1].show = false;
      items[1].disabled = true;
    }
    fixedTagDisabled();
  } else if (currentIndex === 0 || currentPathIsTopRedirect) {
    disabledMenus(true);
  } else {
    disabledMenus(false, prevIsFixedTag);
    fixedTagDisabled();
  }

  return items;
}

/**
 * 右键菜单的落点。
 *
 * 两个刻意的细节，都沿用原实现：贴右边时把菜单往回挪（否则会溢出容器被裁掉）；
 * 隐藏侧边栏时用原始 clientY，否则上移 40px 让出标签栏高度。
 */
export function resolveMenuPosition(input: {
  clientX: number;
  clientY: number;
  containerLeft: number;
  containerWidth: number;
  hiddenSideBar: boolean;
}): { left: number; top: number } {
  const maxLeft = input.containerWidth - MENU_MIN_WIDTH;
  const left = input.clientX - input.containerLeft + 5;
  return {
    left: left > maxLeft ? maxLeft : left,
    top: input.hiddenSideBar ? input.clientY : input.clientY - 40
  };
}
