import { http } from "@/utils/http";

/**
 * FeedLog SSO 令牌（后端 `GET|POST /api/feedlog-token/` 契约，#1998 任务 B）。
 *
 * - `token` 非 null：已登录，令牌可让反馈带上真实身份；
 * - `token` 为 null：**确认未登录**（后端未配置 SSO secret、或该用户没有邮箱，
 *   两种情况都按「无身份」降级），widget 据此走游客模式。
 *
 * 端点**不会返回 401**（未登录也回 200 + null）：401 在 `utils/http` 的响应
 * 拦截器里会触发 `forceLogout()`，把「widget 探测登录态」变成「用户被踢下线」。
 */
export type FeedlogTokenResult = {
  data: { token: string | null };
  message: string;
};

/**
 * 取 FeedLog SSO 令牌。
 *
 * 失败（网络错误 / 超时 / 非 2xx）时**直接 reject**，由调用方决定如何处理——
 * 调用方绝不能把它当成「未登录」吞成 null（见 `plugins/feedlog.ts` 的说明）。
 */
export const getFeedlogToken = () =>
  http.request<FeedlogTokenResult>("get", "/api/feedlog-token/");
