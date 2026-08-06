// 多倍贝文档站主题入口：桥接 @duxweb/vitepress-theme 并注入品牌样式
import { theme } from '@duxweb/vitepress-theme'
import '@duxweb/vitepress-theme/dist/index.css'
// 品牌样式必须在 dux 主题 CSS 之后 import，才能覆盖其默认的 emerald 主色
import './style.css'

// 修复 @duxweb/vitepress-theme 硬编码的英文 UI 文本
// 主题将 "Documentation Navigation" 和 "Reading Time" 写死在组件里，
// langs 配置只能覆盖单位（minute/words）和分隔符，无法覆盖标签本身。
const i18nPatch = {
  'Documentation Navigation': '文档导航',
  'Reading Time': '阅读时长',
}

function patchI18nText() {
  const walker = document.createTreeWalker(
    document.body,
    NodeFilter.SHOW_TEXT,
    null,
    false,
  )
  const nodes: Text[] = []
  let node: Text | null
  while ((node = walker.nextNode() as Text | null)) {
    if (i18nPatch[node.textContent!.trim()]) {
      nodes.push(node)
    }
  }
  nodes.forEach((n) => {
    const trimmed = n.textContent!.trim()
    if (i18nPatch[trimmed]) {
      n.textContent = n.textContent!.replace(trimmed, i18nPatch[trimmed])
    }
  })
}

export default theme.extend({
  Layout: () => {
    // 在客户端路由切换后重新修补文本
    import('vue').then(({ onMounted, watch, nextTick }) => {
      import('vitepress').then((vp) => {
        const { useRoute } = vp
        const route = useRoute()
        onMounted(() => {
          watch(
            () => route.path,
            async () => {
              await nextTick()
              patchI18nText()
            },
            { immediate: true },
          )
        })
      })
    })
    return null // 不包裹额外布局，仅注入副作用
  },
})
