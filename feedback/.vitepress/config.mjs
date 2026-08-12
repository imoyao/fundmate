import { defineConfig } from 'vitepress'
import { withDuxTheme } from '@duxweb/vitepress-theme/config'

// 多多贝反馈中心（feedback.duoduobei.com）
// 技术栈与 docs 站一致（VitePress + @duxweb/vitepress-theme），便于复用构建/部署脚本。
// 反馈内容来自 feedback/index.md（首页 home layout），FeedLog 入口内嵌。
// 品牌色/logo 与主站、文档站、应用站保持一致：主色 #E34F38。
export default withDuxTheme(
  defineConfig({
    title: '多多贝 · 反馈中心',
    description: '多多贝产品（应用站 / 叽咕 / 主站）统一反馈入口。功能建议、Bug 反馈、吐槽，一键送达开发团队。',
    lang: 'zh-CN',
    lastUpdated: true,
    ignoreDeadLinks: true,
    vite: {
      ssr: {
        noExternal: ['@duxweb/vitepress-theme'],
      },
    },
    head: [['link', { rel: 'icon', href: '/logo.svg' }]],
    themeConfig: {
      logo: '/logo.svg',
      nav: [
        { text: '反馈中心', link: '/' },
        { text: '主站', link: 'https://duoduobei.com' },
        { text: '应用站', link: 'https://app.duoduobei.com' },
        { text: '叽咕', link: 'https://jigu.duoduobei.com' },
      ],
      socialLinks: [
        { icon: 'github', link: 'https://github.com/imoyao/fundmate' },
      ],
      footer: {
        message: 'Copyright © 2020-present <a href="https://github.com/imoyao" target="_blank">imoyao</a>',
        copyright: '<a href="https://github.com/imoyao/fundmate" target="_blank">GitHub</a>',
      },
    },
    langs: {
      search: {
        button: { buttonText: '搜索', buttonAriaLabel: '搜索' },
        modal: { noResultsText: '无法找到相关结果' },
      },
      docFooter: {
        prevPageText: '上一页',
        nextPageText: '下一页',
      },
    },
  })
)
