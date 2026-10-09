// 多多贝文档站主题入口：桥接 @duxweb/vitepress-theme 并注入品牌样式
import { theme as baseTheme } from '@duxweb/vitepress-theme'
import '@duxweb/vitepress-theme/dist/index.css'
// 品牌样式必须在 dux 主题 CSS 之后 import，才能覆盖其默认的 emerald 主色
import './style.css'

// theme/ → .vitepress/ → docs/，故组件在 ../../changelog/components/
import ChangelogTimeline from '../../changelog/components/ChangelogTimeline.vue'
// scripts/ 在仓库根，故从 docs/.vitepress/theme/ 需上溯三级
import { loadChangelogEntries } from '../../../scripts/docs/load-changelog.mjs'

// dux 主题是自定义主题对象 { Layout, NotFound, enhanceApp }。
// 中文本地化由 config.mjs 的 `lang: 'zh-CN'` 驱动（见 useLocale.cjs：
// 默认语言从 site.lang 读取，加载 zh-CN locale），无需运行时 DOM patch。
//
// 本仓额外注入两件事：
//   1) `ChangelogTimeline` —— 更新日志时间线组件（docs/changelog/index.md 引用）；
//   2) `changelog-data` 页面数据 —— **构建期**从 FeedLog 拉取（Node 中 fetch，
//      不受浏览器 CORS 限制）。单一真值源是 FeedLog，本仓不维护第二份内容。
//
// 注意：这里显式解构 `enhanceApp` 再回调，而非直接 `...baseTheme` 展开——
// 因为 dux 主题的 enhanceApp 可能带 this 绑定或需要原始 arguments，
// 直接引用会丢失上下文（该主题是外部包，不在本仓控制范围内）。
const theme = {
  ...baseTheme,
  enhanceApp(ctx) {
    if (typeof baseTheme.enhanceApp === 'function') {
      baseTheme.enhanceApp(ctx)
    }
    ctx.app.component('ChangelogTimeline', ChangelogTimeline)
  },
}

export default theme

// ── 构建期数据加载 ────────────────────────────────────────────────
// 失败不抛错：降级为 degraded 标记，页面显示提示而非空白。
// 理由：外部站点抖动不应让整个 docs 构建失败。
export async function changelogData() {
  return await loadChangelogEntries()
}