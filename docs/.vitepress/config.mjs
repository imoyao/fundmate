import { defineConfig } from 'vitepress'
import { withDuxTheme } from '@duxweb/vitepress-theme/config'
import { getSidebar } from 'vitepress-plugin-auto-sidebar'
import { resolve } from 'node:path'

// 多倍贝文档站 · 正式迁移配置（vuepress v1 → VitePress + @duxweb/vitepress-theme）
// 品牌色来自 branding/logo.svg：主色 #E34F38、浅色 #FDFBF7
// 品牌名 / slogan 与主站（落地页、前端 App）保持一致：多倍贝 · 看见你的复利增长
export default withDuxTheme(
  defineConfig({
    title: '多倍贝 · 看见你的复利增长',
    description: '一个帮你算清真实收益、让复利增长清晰可见的投资账本。手动归集、穿透持仓、算准 XIRR，数据始终在你手里。',
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
    themeConfig: {
      nav: [
        { text: '首页', link: '/' },
        { text: '使用', link: '/guide/' },
        { text: '开发', link: '/dev/' },
        { text: '接口', link: '/api/' },
        { text: '测试', link: '/pytest/' },
        { text: '关于', link: '/about/' },
      ],
      // auto-sidebar：自动按目录结构生成侧边栏（替代 vuepress 的 auto-sidebar 插件）
      sidebar: getSidebar({
        contentRoot: 'docs',
        contentDirs: [
          { path: 'guide', title: '使用' },
          { path: 'dev', title: '开发' },
          { path: 'api', title: '接口' },
          { path: 'pytest', title: '测试' },
          { path: 'features', title: '功能' },
          { path: 'spec', title: '规范' },
          { path: 'design', title: '设计' },
          { path: 'site', title: '站点' },
          { path: 'ops', title: '运维' },
          { path: 'working-notes', title: '工作笔记' },
        ],
        collapsible: true,
        collapsed: false,
        useFrontmatter: true,
      }),
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
        message: 'MIT Licensed | Copyright © 2020-present 别院牧志',
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
      readingTime: {
        time: '分钟阅读',
        words: '字',
        minute: '分钟',
        minutes: '分钟',
      },
      sidebar: {
        toggleButtonText: '切换侧边栏',
        mobileTitle: '菜单',
        docNavTitle: '文档导航',
      },
    },
  })
)
