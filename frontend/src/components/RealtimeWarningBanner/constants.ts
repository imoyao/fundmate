/**
 * 实时估值合规横幅的「已关闭」标记键。
 *
 * 为什么单列成模块而不是留在 `index.vue` 里 export：
 * `tsc --noEmit`（CI 类型检查的第一步，早于 vue-tsc）对 `.vue` 走的是
 * `*.vue` 的 wildcard 声明，**只有 default 导出**，因此「从 .vue 具名导入」
 * 在纯 .ts 文件里必然报 TS2614。原先只有 .vue 里的调用方（用 vue-tsc 解析）
 * 不暴露这个问题；一旦有 composable（.ts）要读这个键就立刻炸。
 *
 * 语义：由外层自选页在实时估值功能「关→开」时清除，使横幅重新出现；
 * 横幅自身只在挂载时读取该标记决定初始显隐（关掉后刷新页面不再弹）。
 */
export const REALTIME_BANNER_DISMISS_KEY = "realtime-warning-banner-dismissed";
