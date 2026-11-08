import type { RouteRecordRaw } from "vue-router";

/**
 * 路由工厂（modules/*.ts）接收的配置：在 RouteRecordRaw 上明确子级数组，
 * 避免工厂函数用 any 描述整份配置（#2879）。
 */
export type RouteConfigWithChildren = RouteRecordRaw & {
  children?: RouteRecordRaw[];
};
