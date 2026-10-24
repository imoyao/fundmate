/**
 * ============================================================
 * feedlog.ts
 * FeedLog 反馈 widget 接入（#1997；#1998 任务 B 起接 SSO 身份）
 *
 * 形态演进：
 *   - #1997 起先跑**游客模式**（不传 auth），embed 页首条消息时铸造游客；
 *   - #1998 任务 B 起传 `auth`：**已登录用户的反馈带上真实身份**，
 *     未登录仍自动落回游客模式（后端回 `token: null` ⇒ widget 按游客处理）。
 *   游客提交开关已由 owner 在 FeedLog workspace 打开
 *     （2026-10-20 实测 /api/widget/config 返回 allowGuest: true）。
 *
 * `getToken` 的返回/抛错语义是**硬约束**（官方 SDK 原文，勿改）：
 *   "Throwing signals a temporary failure — the SDK surfaces a retryable
 *    error instead of treating it as signed out."
 *   —— 只有「确认已登出」才回 `null`；网络错误 / 超时 / 响应结构异常一律
 *   **throw**。把临时故障吞成 null 会让 widget 清掉缓存会话，
 *   表现为「用户莫名频繁掉线」（卡面点名的严重回归）。
 *
 * 主题同步为什么不直接用 theme: 'auto'：
 *   'auto' 跟随**系统偏好**；但本仓的主题是用户可覆盖的（utils/theme.ts 的
 *   setThemeMode 把偏好写进 <html> 的 dark class + localStorage）。用户完全
 *   可以「系统亮色 + 应用暗色」。所以初值取当前 class，之后用 MutationObserver
 *   观测 class 变化调 updateWidget——不依赖 setThemeMode / store / 系统偏好
 *   哪条代码路径触发，观测的是**最终落点**，切换方式怎么改都不会失联。
 *
 * zIndex=1050 的来历（卡里原建议 100，实测不成立）：
 *   本仓层叠盘点：sidebar 998/1001/1002、SidebarCenterCollapse 1002、
 *   sidebar 移动端 2001、element-plus.scss 覆盖层 9999、EP 对话框 nextZIndex 2000+。
 *   100 会被左侧 sidebar（998+）压住；1050 高于全部应用 chrome、低于 EP 遮罩与
 *   对话框——反馈面板不该盖住模态框。真机遮挡走查见卡里「任务 4」。
 * ============================================================
 */

import { createWidget, updateWidget, type WidgetTheme } from "@feedlog/widget";
import { getFeedlogToken } from "@/api/feedlog";
import router from "@/router";

/** 反馈站地址（公开端点，无敏感信息；各环境同值，见 .env.example） */
const BASE_URL = import.meta.env.VITE_FEEDLOG_BASE_URL as string | undefined;

/** 模块级幂等标志：HMR / 重复 import 不会二次 createWidget（SDK 本身也忽略重复调用） */
let initialized = false;

/** 当前应用主题：真相源是 <html> 的 dark class（utils/theme.ts 的唯一落点） */
function currentTheme(): WidgetTheme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

/**
 * widget 的身份回调：向后端换一个 FeedLog SSO 令牌（#1998 任务 B）。
 *
 * 三种返回必须严格区分（错一种就出用户可见的回归）：
 * - 拿到令牌 → 返回该字符串（反馈带真实身份）；
 * - 后端明确回 `token: null` → 返回 `null`（**确认未登录**，widget 走游客模式）；
 * - 网络错误 / 超时 / 非 2xx / 响应结构异常 → **throw**（临时故障，SDK 会
 *   提示可重试；吞成 null 会被当成登出，用户缓存会话被清 → 频繁掉线）。
 */
async function getFeedlogTokenForWidget(): Promise<string | null> {
  // 不 catch：让 http 层的失败原样抛给 SDK（它区分「登出」与「临时故障」）
  const res = await getFeedlogToken();
  const payload = res?.data;
  if (!payload || !("token" in payload)) {
    // 结构异常不是「未登录」——按临时故障抛，别让 widget 清会话
    throw new Error("[feedlog] feedlog-token 响应结构异常");
  }
  return payload.token ?? null;
}

/**
 * widget 的「去登录」回调：跳到登录页。
 *
 * SDK 契约：login 返回的 Promise 必须在用户**退出登录 UI 时也 settle**
 * （取消也要 resolve），否则 widget 会一直隐藏。导航失败同样要 settle。
 */
async function loginForWidget(): Promise<void> {
  try {
    await router.push("/login");
  } catch {
    // 导航失败也必须 settle（否则 widget 卡在「等待登录」永不显示）
  }
}

/**
 * 初始化 FeedLog 反馈 widget。
 *
 * 调用约束（官方 SDK 硬性要求）：
 *   - 只能在 client-only 代码里调——本文件由 main.ts 在 app.mount 之后引入，
 *     纯 SPA 无 SSR，满足；
 *   - 面板显隐/更新一律走 updateWidget()，不要重复 createWidget()。
 */
export function initFeedlogWidget(): void {
  if (initialized) return;

  if (!BASE_URL) {
    // 缺配置时静默跳过而不是抛错：反馈是增强功能，不该因它白屏。
    // 但留 warn——CI 若忘记配 env，这里会是唯一线索。
    console.warn("[feedlog] VITE_FEEDLOG_BASE_URL 未配置，反馈 widget 未启用");
    return;
  }

  initialized = true;

  createWidget({
    baseUrl: BASE_URL,
    theme: currentTheme(),
    zIndex: 1050,
    launcher: { alignment: "right", state: "button" },
    // locale 不传：SDK 默认 auto（按浏览器语言解析中/英）
    // auth（#1998）：已登录用户带真实身份提交反馈；未登录由 getToken 回 null
    // 自动落回游客模式（allowGuest 已开），两种身份都能提交。
    auth: {
      getToken: getFeedlogTokenForWidget,
      login: loginForWidget
    }
  });

  // 暗色同步：观测 <html> class 的最终落点，见文件头「主题同步」节。
  const observer = new MutationObserver(() => {
    updateWidget({ theme: currentTheme() });
  });
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"]
  });
}
