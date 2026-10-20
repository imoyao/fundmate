/**
 * ============================================================
 * feedlog.ts
 * FeedLog 反馈 widget 接入（#1997）
 *
 * 形态决策（卡里「先开游客提交跑通链路，不做 SSO」）：
 *   - **不传 auth**：widget 以游客身份运行，由 embed 页首条消息时铸造游客。
 *     SSO（Flask 加 /api/feedlog-token 签 JWT）是后续独立卡，不塞进本卡。
 *   - 游客提交开关已由 owner 在 FeedLog workspace 打开
 *     （2026-10-20 实测 /api/widget/config 返回 allowGuest: true）。
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

/** 反馈站地址（公开端点，无敏感信息；各环境同值，见 .env.example） */
const BASE_URL = import.meta.env.VITE_FEEDLOG_BASE_URL as string | undefined;

/** 模块级幂等标志：HMR / 重复 import 不会二次 createWidget（SDK 本身也忽略重复调用） */
let initialized = false;

/** 当前应用主题：真相源是 <html> 的 dark class（utils/theme.ts 的唯一落点） */
function currentTheme(): WidgetTheme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
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
    launcher: { alignment: "right", state: "button" }
    // locale 不传：SDK 默认 auto（按浏览器语言解析中/英）
    // auth 不传：游客模式（见文件头形态决策）
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
