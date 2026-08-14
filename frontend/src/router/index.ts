// import "@/utils/sso";
import Cookies from "js-cookie";
import { getConfig } from "@/config";
import NProgress from "@/utils/progress";
import { buildHierarchyTree } from "@/utils/tree";
import remainingRouter from "./modules/remaining";
import { useMultiTagsStoreHook } from "@/store/modules/multiTags";
import { usePermissionStoreHook } from "@/store/modules/permission";
import {
  isUrl,
  openLink,
  cloneDeep,
  isAllEmpty,
  storageLocal
} from "@pureadmin/utils";
import {
  ascending,
  getTopMenu,
  isOneOfArray,
  getHistoryMode,
  findRouteByPath,
  handleAliveRoute,
  formatTwoStageRoutes,
  formatFlatteningRoutes
} from "./utils";
import {
  type Router,
  type RouteRecordRaw,
  type RouteComponent,
  createRouter
} from "vue-router";
import {
  type DataInfo,
  userKey,
  removeToken,
  multipleTabsKey
} from "@/utils/auth";
import { getMe, type MeResult } from "@/api/auth";

// ============================================
// 🔥 Supabase 集成
// ============================================
import { supabase } from "@/utils/supabase";

/** 自动导入全部静态路由，无需再手动引入！匹配 src/router/modules 目录（任何嵌套级别）中具有 .ts 扩展名的所有文件，除了 remaining.ts 文件
 * 如何匹配所有文件请看：https://github.com/mrmlnc/fast-glob#basic-syntax
 * 如何排除文件请看：https://cn.vitejs.dev/guide/features.html#negative-patterns
 */
const modules: Record<string, any> = import.meta.glob(
  ["./modules/**/*.ts", "!./modules/**/remaining.ts"],
  {
    eager: true
  }
);

/** 原始静态路由（未做任何处理） */
const routes = [];

Object.keys(modules).forEach(key => {
  routes.push(modules[key].default);
});

/** 导出处理后的静态路由（三级及以上的路由全部拍成二级） */
export const constantRoutes: Array<RouteRecordRaw> = formatTwoStageRoutes(
  formatFlatteningRoutes(buildHierarchyTree(ascending(routes.flat(Infinity))))
);

/** 初始的静态路由，用于退出登录时重置路由 */
const initConstantRoutes: Array<RouteRecordRaw> = cloneDeep(constantRoutes);

/** 用于渲染菜单，保持原始层级 */
export const constantMenus: Array<RouteComponent> = ascending(
  routes.flat(Infinity)
).concat(...remainingRouter);

/** 不参与菜单的路由 */
export const remainingPaths = Object.keys(remainingRouter).map(v => {
  return remainingRouter[v].path;
});

/** 创建路由实例 */
export const router: Router = createRouter({
  history: getHistoryMode(import.meta.env.VITE_ROUTER_HISTORY),
  routes: constantRoutes.concat(...(remainingRouter as any)),
  strict: true,
  scrollBehavior(to, from, savedPosition) {
    return new Promise(resolve => {
      if (savedPosition) {
        return savedPosition;
      } else {
        if (from.meta.saveSrollTop) {
          const top: number =
            document.documentElement.scrollTop || document.body.scrollTop;
          resolve({ left: 0, top });
        }
      }
    });
  }
});

/** 记录已经加载的页面路径 */
const loadedPaths = new Set<string>();

/** 重置已加载页面记录 */
export function resetLoadedPaths() {
  loadedPaths.clear();
}

/** 重置路由 */
export function resetRouter() {
  router.clearRoutes();
  for (const route of initConstantRoutes.concat(...(remainingRouter as any))) {
    router.addRoute(route);
  }
  router.options.routes = formatTwoStageRoutes(
    formatFlatteningRoutes(buildHierarchyTree(ascending(routes.flat(Infinity))))
  );
  usePermissionStoreHook().clearAllCachePage();
  resetLoadedPaths();
}

/** 路由白名单（不需要登录即可访问） */
const whiteList = ["/login", "/explore", "/access-denied"];

const { VITE_HIDE_HOME } = import.meta.env;

// ============================================
// 🔥 路由守卫（Supabase 认证）
// ============================================
router.beforeEach(async (to: ToRouteType, _from, next) => {
  to.meta.loaded = loadedPaths.has(to.path);

  if (!to.meta.loaded) {
    NProgress.start();
  }

  if (to.meta?.keepAlive) {
    handleAliveRoute(to, "add");
    if (_from.name === undefined || _from.name === "Redirect") {
      handleAliveRoute(to);
    }
  }

  // ============================================
  // 🔥 核心改动：使用 Supabase 验证登录状态
  // ============================================
  const { data } = await supabase.auth.getSession();
  const isAuthenticated = !!data.session;

  // 获取本地存储的用户信息（用于角色/权限判断）
  const userInfo = storageLocal().getItem<DataInfo<number>>(userKey);

  // 同步状态：如果 Supabase 有 session 但本地没有 userInfo，则从后端拉取权威资料
  if (isAuthenticated && !userInfo && data.session?.user) {
    // 从 Supabase 用户信息构造 DataInfo
    const supabaseUser = data.session.user;
    // 邮箱/手机号仅作最后兜底（隐私信息，不应常驻顶栏）；优先用后端返回的登录名与昵称
    const fallbackUsername = supabaseUser.email || supabaseUser.phone || "";
    let meData: MeResult["data"] | undefined;
    try {
      const meResp = await getMe();
      meData = meResp.data;
    } catch (e) {
      // 后端取数失败不阻塞登录，回退到 session 兜底信息
      console.warn("获取用户资料失败，回退到 session 信息：", e);
    }
    const userData: DataInfo<number> = {
      // @ts-ignore - 兼容现有类型
      id: supabaseUser.id,
      // 元数据仅兜底 roles（权限判断用），其余字段以后端权威值为准
      roles: supabaseUser.user_metadata?.roles || ["user"],
      ...supabaseUser.user_metadata,
      // 展示名优先昵称，回退登录名；邮箱仅作最后兜底，避免顶栏直接暴露邮箱
      username: meData?.username || fallbackUsername,
      nickname: meData?.nickname || "",
      avatar: meData?.avatar || supabaseUser.user_metadata?.avatar || ""
    };
    storageLocal().setItem(userKey, userData);
    // 也设置 cookie（兼容现有逻辑）
    Cookies.set(multipleTabsKey, "true", { expires: 7 });
    // 同步到 Pinia store：localStorage 写入不会触发顶栏响应式更新，
    // 必须显式 SET_* 才能让右上角（用户名/昵称）即时刷新
    const { useUserStoreHook } = await import("@/store/modules/user");
    const userStore = useUserStoreHook();
    userStore.SET_USERNAME(userData.username || "");
    userStore.SET_NICKNAME(userData.nickname || "");
    if (userData.avatar) userStore.SET_AVATAR(userData.avatar);
  }

  // 如果 Supabase 没有 session，但本地有 cookie，清理掉
  if (!isAuthenticated && Cookies.get(multipleTabsKey)) {
    removeToken();
  }

  // ============================================
  // 外部链接处理
  // ============================================
  const externalLink = isUrl(to?.name as string);
  if (!externalLink) {
    to.matched.some(item => {
      if (!item.meta.title) return "";
      const Title = getConfig().Title;
      if (Title) document.title = `${item.meta.title} | ${Title}`;
      else document.title = item.meta.title as string;
    });
  }

  function toCorrectRoute() {
    whiteList.includes(to.fullPath) ? next(_from.fullPath) : next();
  }

  // ============================================
  // 🔥 登录状态判断（使用 Supabase session）
  // ============================================
  // 登录状态以 Supabase 会话为准（cookie 只是多标签共享标记，非信任依据）
  if (isAuthenticated) {
    // 确保多标签标记 cookie 存在，避免刷新/重开后整树渲染依赖缺失
    if (!Cookies.get(multipleTabsKey)) {
      Cookies.set(multipleTabsKey, "true", { expires: 7 });
    }
    // 🔥 探市页面独立布局，直接放行
    if (to.path === "/explore") {
      next();
      return;
    }
    // ✅ 已登录用户
    if (to.meta?.roles && !isOneOfArray(to.meta?.roles, userInfo?.roles)) {
      next({ path: "/error/403" });
      return;
    }
    if (VITE_HIDE_HOME === "true" && to.fullPath === "/welcome") {
      next({ path: "/error/404" });
    }
    if (_from?.name) {
      if (externalLink) {
        openLink(to?.name as string);
        NProgress.done();
      } else {
        toCorrectRoute();
      }
    } else {
      // 首次访问时用静态菜单直接填充，跳过异步拉取
      if (
        usePermissionStoreHook().wholeMenus.length === 0 &&
        to.path !== "/login"
      ) {
        // 统一走标准菜单组装（与登录路径一致），避免「总览」等 showLink:false 目录项丢失
        usePermissionStoreHook().handleWholeMenus([]);
        if (!useMultiTagsStoreHook().getMultiTagsCache) {
          const route = findRouteByPath(
            to.path,
            router.options.routes[0]?.children
          );
          getTopMenu(true);
          if (route && route.meta?.title) {
            if (isAllEmpty(route.parentId) && route.meta?.backstage) {
              const { path, name, meta } = route.children[0];
              useMultiTagsStoreHook().handleTags("push", { path, name, meta });
            } else {
              const { path, name, meta } = route;
              useMultiTagsStoreHook().handleTags("push", { path, name, meta });
            }
          }
        }
      }
      next();
    }
  } else {
    // ❌ 未登录用户
    if (to.path !== "/login") {
      if (
        whiteList.indexOf(to.path) !== -1 ||
        to.meta?.requiresAuth === false
      ) {
        // 兜底：已通过 Supabase 认证（isAuthenticated 为真），但因 multipleTabsKey
        // cookie 缺失未进入上方「首次访问」分支，导致 wholeMenus 始终为空、
        // 侧边栏 v-loading（依赖 wholeMenus.length === 0）一直转。
        // 此处用静态菜单填充，确保放行进入的页面侧边栏能正常渲染。
        if (
          isAuthenticated &&
          usePermissionStoreHook().wholeMenus.length === 0
        ) {
          usePermissionStoreHook().handleWholeMenus([]);
        }
        next();
      } else {
        // 清理残留数据
        removeToken();
        next({ path: "/login" });
      }
    } else {
      next();
    }
  }
});

router.afterEach(to => {
  loadedPaths.add(to.path);
  NProgress.done();
});

export default router;
