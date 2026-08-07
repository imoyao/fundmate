// 多倍贝文档站主题入口：桥接 @duxweb/vitepress-theme 并注入品牌样式
import { theme } from '@duxweb/vitepress-theme'
import '@duxweb/vitepress-theme/dist/index.css'
// 品牌样式必须在 dux 主题 CSS 之后 import，才能覆盖其默认的 emerald 主色
import './style.css'
import { h, defineComponent, onMounted } from 'vue'

// 修复 @duxweb/vitepress-theme 硬编码的英文 UI 文本
// 主题将 "Documentation Navigation" 和 "Reading Time" 写死在组件模板里，
// langs 配置只能覆盖单位（minute/words）和分隔符，无法覆盖标签本身。
// 这里通过覆盖 Layout 组件，在 mounted 后做一次 DOM 文本替换。
const PATCH_MAP: Record<string, string> = {
  'Documentation Navigation': '文档导航',
  'Reading Time': '阅读时长',
}

function patchI18nText() {
  if (typeof document === 'undefined') return
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  let node: Text | null
  while ((node = walker.nextNode() as Text | null)) {
    const trimmed = node.textContent?.trim()
    if (trimmed && PATCH_MAP[trimmed]) nodes.push(node)
  }
  nodes.forEach((n) => {
    const trimmed = n.textContent!.trim()
    n.textContent = n.textContent!.replace(trimmed, PATCH_MAP[trimmed])
  })
}

// 包装原 dux Layout，挂载后执行 i18n 文本替换
const LayoutWrapper = defineComponent({
  name: 'FundMateLayout',
  setup() {
    onMounted(() => {
      // 延迟执行，确保 dux Layout 的 DOM 已渲染完成
      setTimeout(patchI18nText, 0)
    })
    return () => h(theme.Layout!)
  },
})

// dux 主题是纯自定义主题对象 { Layout, NotFound, enhanceApp }，不是 VitePress 的
// DefaultTheme，因此不能调用 theme.extend()——直接覆盖 Layout 即可。
export default {
  ...theme,
  Layout: LayoutWrapper,
}
