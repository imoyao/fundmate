// 多多贝文档站主题入口：桥接 @duxweb/vitepress-theme 并注入品牌样式
import { theme } from '@duxweb/vitepress-theme'
import '@duxweb/vitepress-theme/dist/index.css'
// 品牌样式必须在 dux 主题 CSS 之后 import，才能覆盖其默认的 emerald 主色
import './style.css'

// dux 主题是自定义主题对象 { Layout, NotFound, enhanceApp }。
// 中文本地化由 config.mjs 的 `lang: 'zh-CN'` 驱动（见 useLocale.cjs：
// 默认语言从 site.lang 读取，加载 zh-CN locale），无需运行时 DOM patch。
export default theme
