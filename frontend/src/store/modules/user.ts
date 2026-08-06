import { defineStore } from "pinia";
import {
  type userType,
  store,
  router,
  resetRouter,
  routerArrays,
  storageLocal
} from "../utils";
import { logoutApi } from "@/api/auth";
import { useMultiTagsStoreHook } from "./multiTags";
import { type DataInfo, removeToken, userKey } from "@/utils/auth";
import { supabase } from "@/utils/supabase";

export const useUserStore = defineStore("pure-user", {
  state: (): userType => ({
    // 头像
    avatar: storageLocal().getItem<DataInfo<number>>(userKey)?.avatar ?? "",
    // 用户名
    username: storageLocal().getItem<DataInfo<number>>(userKey)?.username ?? "",
    // 昵称
    nickname: storageLocal().getItem<DataInfo<number>>(userKey)?.nickname ?? "",
    // 页面级别权限
    roles: storageLocal().getItem<DataInfo<number>>(userKey)?.roles ?? [],
    // 按钮级别权限
    permissions:
      storageLocal().getItem<DataInfo<number>>(userKey)?.permissions ?? [],
    // 是否勾选了登录页的免登录
    isRemembered: false,
    // 登录页的免登录存储几天，默认7天
    loginDay: 7
  }),
  actions: {
    /** 存储头像 */
    SET_AVATAR(avatar: string) {
      this.avatar = avatar;
    },
    /** 存储用户名 */
    SET_USERNAME(username: string) {
      this.username = username;
    },
    /** 存储昵称 */
    SET_NICKNAME(nickname: string) {
      this.nickname = nickname;
    },
    /** 存储角色 */
    SET_ROLES(roles: Array<string>) {
      this.roles = roles;
    },
    /** 存储按钮级别权限 */
    SET_PERMS(permissions: Array<string>) {
      this.permissions = permissions;
    },
    /** 存储是否勾选了登录页的免登录 */
    SET_ISREMEMBERED(bool: boolean) {
      this.isRemembered = bool;
    },
    /** 设置登录页的免登录存储几天 */
    SET_LOGINDAY(value: number) {
      this.loginDay = Number(value);
    },
    /** 登出：统一走后端 /api/auth/logout，由后端负责服务端作废会话 */
    async logOut() {
      try {
        const { data } = await supabase.auth.getSession();
        const token = data.session?.access_token ?? null;
        await logoutApi(token);
      } catch (e) {
        // 后端登出失败也不阻塞前端退出
        console.warn("后端退出接口调用失败，仍继续前端清理：", e);
      } finally {
        await this.forceLogout();
      }
    },
    /** 强制退出（401 会话失效时调用）：仅清理本地状态并回登录页，不再请求后端，避免死循环 */
    async forceLogout() {
      this.username = "";
      this.roles = [];
      this.permissions = [];
      removeToken();
      // 清本地 Supabase session（local 仅清本地存储，不发网络请求）
      supabase.auth.signOut({ scope: "local" }).catch(() => {});
      useMultiTagsStoreHook().handleTags("equal", [...routerArrays]);
      resetRouter();
      router.push("/login");
    }
  }
});

export function useUserStoreHook() {
  return useUserStore(store);
}
