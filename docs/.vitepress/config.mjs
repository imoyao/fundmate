import { defineConfig } from 'vitepress'
import { withDuxTheme } from '@duxweb/vitepress-theme/config'
import { getSidebar } from 'vitepress-plugin-auto-sidebar'
import { resolve } from 'node:path'

// 多倍贝文档站 · 正式迁移配置（vuepress v1 → VitePress + @duxweb/vitepress-theme）
// 品牌色来自 branding/logo.svg：主色 #E34F38、浅色 #FDFBF7
// 品牌名 / slogan 与主站（落地页、前端 App）保持一致：多倍贝 · 看见你的复利增长
// 修复 vitepress-plugin-auto-sidebar 在 Windows 下生成的链接问题：
// 1) 插件用 path.resolve + String.replace 生成 link，Windows 下会得到反斜杠（\guide\foo.md）；
// 2) 只去掉 contentRoot 前缀，.md 后缀残留。
// VitePress 需要正斜杠、无 .md 的干净路由（/guide/foo），否则侧边栏点击 → 404。
function normalizeSidebar(sidebar) {
  const fix = (items) =>
    (items || []).map((it) => {
      const n = { ...it }
      if (typeof n.link === 'string') {
        n.link = n.link.replace(/\\/g, '/').replace(/\.md$/, '')
      }
      if (n.items) n.items = fix(n.items)
      return n
    })
  return (sidebar || []).map((g) => ({ ...g, items: fix(g.items) }))
}

export default withDuxTheme(
  defineConfig({
    title: '多倍贝 · 看见你的复利增长',
    description: '一个让复利增长清晰可见的投资账本手动归集、穿透持仓、算准 XIRR，数据始终在你手里。',
    // 站点语言：让 @duxweb/vitepress-theme 的 useLocale 直接加载 zh-CN 中文 locale，
    // 否则默认 en-US 会使侧边栏标题(docNavTitle)与阅读时长(time)等 UI 文本显示英文。
    // 见 node_modules/@duxweb/vitepress-theme/dist/cjs/composables/useLocale.cjs
    lang: 'zh-CN',
      // 访问管控：srcExclude 使这些源文件/目录根本不参与构建，不进入产物（dist），
      // 远端用户访问即 404。源文件仍保留在仓库源码中。glob 相对于 srcDir（即 docs/）。
      // 屏蔽清单与说明见 docs/spec/internal-index.md。
      srcExclude: [
        'working-notes/**',
        'backend-restructure-edgeone-dualengine.md',
        'bias-datasource-troubleshooting.md',
        'erniao-ingest-research-2026-08-02.md',
        'overview-bias-stale-2026-08-02.md',
      ],
      // 采用 VitePress 默认的 outDir(.vitepress/dist) 与 publicDir，二者天然分离避免冲突。
      // 部署时发布 docs/.vitepress/dist。logo 放在默认 publicDir 下由构建自动复制。
      lastUpdated: true,
      // 与原 vuepress 行为一致：不阻断构建于历史遗留死链（仓库根 README / frontend/README 的
      // localhost 开发地址、dev/flask-admin 的 localhost:5000、site/donate·todo 的目录链接被解析为
      // /xxx/index 的软死链）。死链清理作为独立的文档 tech-debt（见 docs/spec/tech-debt.md）后续处理。
      ignoreDeadLinks: true,
    // 第三方 ESM 主题/插件在 config 预构建阶段需 ESM 化，避免被 externalize 成 require 加载而找不到 vitepress 的具名导出
    vite: {
      ssr: {
        noExternal: ['@duxweb/vitepress-theme', 'vitepress-plugin-auto-sidebar'],
      },
    },
    markdown: {
      // 脚注原生支持（原 vuepress md-enhance 的 footnote 能力）
      footnote: true,
      image: { lazyLoading: true },
    },
    // 站点图标：logo 与 favicon 来自 logo-delivery（正式稿），置于默认 publicDir(.vitepress/public)
    head: [
      ['link', { rel: 'icon', href: '/favicon.ico' }],
    ],
    themeConfig: {
      logo: '/logo.svg',
      nav: [
        { text: '首页', link: '/' },
        { text: '使用', link: '/guide/' },
        { text: '功能', link: '/features/' },
        { text: '接口', link: '/api/' },
        { text: '关于', link: '/about/' },
      ],
      // auto-sidebar：自动按目录结构生成侧边栏（替代 vuepress 的 auto-sidebar 插件）
      // 注：该插件在 Windows 下生成的 link 含反斜杠且残留 .md，须经 normalizeSidebar 修正
      sidebar: normalizeSidebar(getSidebar({
        contentRoot: 'docs',
        contentDirs: [
          { path: 'guide', title: '使用' },
          { path: 'dev', title: '开发' },
          { path: 'api', title: '接口' },
          { path: 'pytest', title: '测试' },
          { path: 'features', title: '功能' },
          { path: 'spec', title: '规范' },
          { path: 'design', title: '设计' },
          { path: 'ops', title: '运维' },
        ],
        collapsible: true,
        collapsed: false,
        useFrontmatter: true,
      })),
      socialLinks: [
        { icon: 'github', link: 'https://github.com/imoyao/fundmate' },
      ],
      search: true,
      lastUpdatedText: '最后更新',
      // 对应原 vuepress 的 repo / docsDir / docsBranch / editLinks
      editLink: {
        pattern: 'https://github.com/imoyao/fundmate/edit/docs/:path',
        text: '在 GitHub 上编辑此页',
      },
      footer: {
        message: 'Copyright © 2020-present <a href="https://github.com/imoyao" target="_blank">imoyao</a>',
        copyright: '<a href="https://github.com/imoyao/fundmate" target="_blank">GitHub</a>',
      },
    },
    // 中文多语言文本适配（搜索 / 编辑链接 / 阅读时长）
    langs: {
      search: {
        button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
        modal: {
          noResultsText: '无法找到相关结果',
          footer: {
            selectText: '选择',
            navigateText: '切换',
            closeText: '关闭',
            selectKeyAriaLabel: 'enter',
            navigateUpKeyAriaLabel: 'up arrow',
            navigateDownKeyAriaLabel: 'down arrow',
            closeKeyAriaLabel: 'escape',
          },
        },
      },
      docFooter: {
        editLinkText: '在 GitHub 上编辑此页',
        lastUpdatedText: '最后更新',
        prevPageText: '上一页',
        nextPageText: '下一页',
      },
      // 注：readingTime 与 sidebar.docNavTitle 不再在此覆盖 —— 设 lang:'zh-CN' 后
      // 主题会直接加载 zh-CN locale 默认值（"阅读时间" / "文档导航"），避免与 locale 冲突。
    },
  })
)
