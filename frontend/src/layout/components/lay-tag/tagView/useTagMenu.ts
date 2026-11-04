/**
 * 标签栏的「关哪几个 / 菜单怎么摆」（#980 拆分自 layout/components/lay-tag/index.vue）。
 *
 * 这里放的是**有副作用的编排**：删标签（写 store + 跳路由 + 刷新 keep-alive）、
 * 右键菜单落点、下拉菜单分发。判断逻辑已经抽到 `tagMenuModel.ts`，本文件只负责
 * 把判断结果写回 `tagsViews`、把动作派给 router / store。
 */

import { nextTick, toRaw, unref } from "vue";
import type { Ref } from "vue";
import NProgress from "@/utils/progress";
import { getTopMenu, handleAliveRoute } from "@/router/utils";
import { routerArrays } from "@/layout/types";
import { useSettingStoreHook } from "@/store/modules/settings";
import { useMultiTagsStoreHook } from "@/store/modules/multiTags";
import { usePermissionStoreHook } from "@/store/modules/permission";
import type { RouteConfigs } from "../../../types";
import {
  MENU_INDEX,
  applyMenuBody,
  resolveMenuIndex,
  resolveMenuModel,
  resolveMenuPosition,
  snapshotMenuBody
} from "./tagMenuModel";

import ExitFullscreen from "~icons/ri/fullscreen-exit-fill";
import Fullscreen from "~icons/ri/fullscreen-fill";

/**
 * 标签栏菜单编排。
 *
 * 依赖全部由调用方显式传入（不在这里重新 `useTags()`）：`tagsViews` 是
 * `reactive` 数组、`visible` 等是 `ref`，重新调 `useTags()` 会拿到**另一份实例**，
 * 改那份对界面无效——这是拆分时最容易踩的坑。
 */
export function useTagMenu(options: {
  route: any;
  router: any;
  multiTags: Ref<any[]>;
  tagsViews: any[];
  currentSelect: Ref<any>;
  visible: Ref<boolean>;
  buttonTop: Ref<number>;
  buttonLeft: Ref<number>;
  containerDom: Ref<HTMLDivElement | undefined>;
  closeMenu: () => void;
  onContentFullScreen: () => void;
  dynamicTagView: () => Promise<void>;
}) {
  const {
    route,
    router,
    multiTags,
    tagsViews,
    currentSelect,
    visible,
    buttonTop,
    buttonLeft,
    containerDom,
    closeMenu,
    onContentFullScreen,
    dynamicTagView
  } = options;

  const topPath = getTopMenu()?.path;
  const { VITE_HIDE_HOME } = import.meta.env;
  const fixedTags = [
    ...routerArrays,
    ...usePermissionStoreHook().flatteningRoutes.filter(v => v?.meta?.fixedTag)
  ];

  /** 刷新路由：走 /redirect 中转，让 keep-alive 缓存失效 */
  function onFresh() {
    NProgress.start();
    const { fullPath, query } = unref(route);
    router.replace({ path: "/redirect" + fullPath, query });
    handleAliveRoute(route as ToRouteType, "refresh");
    NProgress.done();
  }

  /** 关闭类菜单项整体显示/隐藏（下拉菜单复用同一份状态） */
  function showMenus(value: boolean) {
    applyMenuBody(
      tagsViews,
      snapshotMenuBody(tagsViews).map(state => ({ ...state, show: value }))
    );
  }

  function disabledMenus(value: boolean, fixedTag = false) {
    const states = snapshotMenuBody(tagsViews).map(state => ({
      ...state,
      disabled: value
    }));
    if (fixedTag) {
      // 「关闭左侧」（MENU_INDEX.closeLeft）：左侧是固定标签时无从关起
      states[1] = { show: false, disabled: true };
    }
    applyMenuBody(tagsViews, states);
  }

  /**
   * 推导并写回关闭类菜单项状态。
   *
   * `refresh` 为真时额外放开「重新加载」——只有「右键的是当前标签」才允许刷新，
   * 与左侧那些关闭项不同，这一项不受 `showMenus` 管辖，必须单独设。
   */
  function showMenuModel(
    currentPath: string,
    query: object = {},
    params: object = {},
    refresh = false
  ) {
    const allRoute = multiTags.value;
    const currentIndex = resolveMenuIndex(allRoute, {
      path: currentPath,
      query,
      params
    });

    if (refresh) tagsViews[MENU_INDEX.refresh].show = true;

    applyMenuBody(
      tagsViews,
      resolveMenuModel({
        current: snapshotMenuBody(tagsViews),
        routeLength: multiTags.value.length,
        currentIndex,
        currentIsFixedTag: Boolean(allRoute[currentIndex]?.meta?.fixedTag),
        prevIsFixedTag: Boolean(allRoute[currentIndex - 1]?.meta?.fixedTag),
        currentPathIsTopRedirect: currentPath === `/redirect${topPath}`
      })
    );
  }

  /**
   * 删除标签并决定接下来去哪个路由。
   *
   * `tag` 是「删除范围」：`left` / `right` / `other` 对应批量删除，缺省是只删当前。
   * 删的若是**当前激活标签**，要自动切到剩下的第一个；删的是别人则只在必要时回补。
   */
  function deleteDynamicTag(obj: any, current: string, tag?: string) {
    // 注意：这里的匹配用 `===` 比较 query/params 字符串，与 showMenuModel 的
    // `isEqual` 深比较**不是同一套口径**，不可合并——标签里的 query 是路由序列化产物。
    const valueIndex: number = multiTags.value.findIndex((item: any) => {
      if (item.query) {
        if (item.path === obj.path) return item.query === obj.query;
      } else if (item.params) {
        if (item.path === obj.path) return item.params === obj.params;
      } else {
        return item.path === obj.path;
      }
    });

    const spliceRoute = (
      startIndex?: number,
      length?: number,
      other?: boolean
    ): void => {
      if (other) {
        useMultiTagsStoreHook().handleTags(
          "equal",
          [
            VITE_HIDE_HOME === "false" ? fixedTags : toRaw(getTopMenu()),
            obj
          ].flat()
        );
      } else {
        useMultiTagsStoreHook().handleTags("splice", "", {
          startIndex,
          length
        }) as any;
      }
      void dynamicTagView();
    };

    if (tag === "other") {
      spliceRoute(1, 1, true);
    } else if (tag === "left") {
      spliceRoute(fixedTags.length, valueIndex - fixedTags.length);
    } else if (tag === "right") {
      spliceRoute(valueIndex + 1, multiTags.value.length);
    } else {
      spliceRoute(valueIndex, 1);
    }

    const newRoute = useMultiTagsStoreHook().handleTags("slice");
    const jumpToFirst = () => {
      if (newRoute[0]?.query) {
        router.push({ name: newRoute[0].name, query: newRoute[0].query });
      } else if (newRoute[0]?.params) {
        router.push({ name: newRoute[0].name, params: newRoute[0].params });
      } else {
        router.push({ path: newRoute[0].path });
      }
    };

    if (current === route.path) {
      // 删掉的是当前激活标签：自动切到剩下的第一个
      if (tag === "left") return;
      jumpToFirst();
    } else {
      if (!multiTags.value.length) return;
      if (multiTags.value.some(item => item.path === route.path)) return;
      jumpToFirst();
    }
  }

  function deleteMenu(item, tag?: string) {
    deleteDynamicTag(item, item.path, tag);
    handleAliveRoute(route as ToRouteType);
  }

  /** 同步「内容区全屏」两处入口的文案/图标（常显按钮 + 倒三角菜单项） */
  function syncFullScreenMenuState() {
    // 菜单项可能尚未初始化（tagsViews[6] 为 undefined），且状态更新要等渲染；
    // 与原实现一致用 100ms 兜底，并对空值判保护，避免点击时报错或文案不同步。
    setTimeout(() => {
      const tag = tagsViews[MENU_INDEX.fullscreen];
      if (!tag) return;
      tag.icon = useSettingStoreHook().hiddenSideBar
        ? ExitFullscreen
        : Fullscreen;
      tag.text = useSettingStoreHook().hiddenSideBar
        ? "退出内容区全屏"
        : "内容区全屏";
    }, 100);
  }

  /** 外部常显按钮的切换入口：切换 hiddenSideBar 并同步菜单项状态 */
  function toggleContentFullScreen() {
    onContentFullScreen();
    syncFullScreenMenuState();
  }

  /** 下拉菜单/右键菜单的统一分发（下标含义见 MENU_INDEX） */
  function onClickDrop(key: number, item: any, selectRoute?: RouteConfigs) {
    if (item && item.disabled) return;

    const selectTagRoute = selectRoute
      ? {
          path: selectRoute.path,
          meta: selectRoute.meta,
          name: selectRoute.name,
          query: selectRoute?.query,
          params: selectRoute?.params
        }
      : { path: route.path, meta: route.meta };

    switch (key) {
      case MENU_INDEX.refresh:
        onFresh();
        break;
      case MENU_INDEX.closeCurrent:
        deleteMenu(selectTagRoute);
        break;
      case MENU_INDEX.closeLeft:
        deleteMenu(selectTagRoute, "left");
        break;
      case MENU_INDEX.closeRight:
        deleteMenu(selectTagRoute, "right");
        break;
      case MENU_INDEX.closeOther:
        deleteMenu(selectTagRoute, "other");
        break;
      case MENU_INDEX.closeAll:
        useMultiTagsStoreHook().handleTags("splice", "", {
          startIndex: fixedTags.length,
          length: multiTags.value.length
        });
        router.push(topPath);
        handleAliveRoute(route as ToRouteType);
        break;
      case MENU_INDEX.fullscreen:
        // 与常显按钮共用同一逻辑，保证两处文案/状态同步
        onContentFullScreen();
        syncFullScreenMenuState();
        break;
    }
    setTimeout(() => {
      showMenuModel(route.fullPath, route.query, route.params);
    });
  }

  function handleCommand(command: any) {
    const { key, item } = command;
    onClickDrop(key, item);
  }

  /** 触发右键菜单里的点击（右键菜单作用于 `currentSelect`，不是当前路由） */
  function selectTag(key: number, item: any) {
    closeMenu();
    onClickDrop(key, item, currentSelect.value);
  }

  /**
   * 打开右键菜单：先按「右键的是谁」把菜单项摆好，再把菜单挪到鼠标位置。
   *
   * 三种特殊情形原样保留：右键固定标签（含顶级菜单）只给「重新加载」；
   * 右键的不是当前标签则隐藏「重新加载」；只剩两个标签时不给「关闭其他」。
   */
  function openMenu(tag: any, e: MouseEvent) {
    closeMenu();
    if (tag.path === topPath || tag?.meta?.fixedTag) {
      showMenus(false);
      tagsViews[MENU_INDEX.refresh].show = true;
    } else if (route.path !== tag.path && route.name !== tag.name) {
      tagsViews[MENU_INDEX.refresh].show = false;
      showMenuModel(tag.path, tag.query, tag.params);
    } else if (multiTags.value.length === 2 && route.path !== tag.path) {
      showMenus(true);
      // 只有两个标签时「关闭其他」没有意义
      tagsViews[MENU_INDEX.closeOther].show = false;
      showMenuModel(tag.path, tag.query, tag.params);
    } else {
      showMenuModel(tag.path, tag.query, tag.params, true);
    }

    currentSelect.value = tag;
    const container = unref(containerDom) as HTMLElement;
    const position = resolveMenuPosition({
      clientX: e.clientX,
      clientY: e.clientY,
      containerLeft: container.getBoundingClientRect().left,
      containerWidth: container.offsetWidth,
      hiddenSideBar: useSettingStoreHook().hiddenSideBar
    });
    buttonLeft.value = position.left;
    buttonTop.value = position.top;
    nextTick(() => {
      visible.value = true;
    });
  }

  return {
    showMenus,
    disabledMenus,
    showMenuModel,
    openMenu,
    onClickDrop,
    handleCommand,
    selectTag,
    deleteMenu,
    onFresh,
    toggleContentFullScreen,
    syncFullScreenMenuState
  };
}
