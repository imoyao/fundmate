module.exports = {
    title: '基伴',
    description: '基金理财好伙伴！',
    theme: 'antdocs',
    // 释出目录
    dest: 'docs/public',
    plugins: [
        "vuepress-plugin-auto-sidebar", {},
        ['homebadge', {
            selector: '.hero',
            repoLink: 'https://github.com/zpfz/vuepress-theme-antdocs',
            badgeLink: 'https://img.shields.io/badge/link-996.icu-red.svg',
            // badgeGroup: [
            //     'https://img.shields.io/badge/build-passing-brightgreen?style=flat-square',
            //     'https://img.shields.io/npm/dt/vuepress-theme-antdocs?style=flat-square&color=red',
            //     'https://img.shields.io/github/license/zpfz/vuepress-theme-antdocs?style=flat-square&color=blue',
            //     'https://img.shields.io/npm/v/vuepress-theme-antdocs?style=flat-square'
            // ]
        }]],
    themeConfig: {
        nav: [
            {text: '首页', link: '/'},
            {text: '使用', link: '/user/'},
            {text: '开发', link: '/dev/'},
            {text: '部署', link: '/guide/'},
            {text: '接口', link: '/api/'},
            {
                text: '更多',
                items: [
                    {text: '反馈', link: '/feedback/'},
                    {text: 'FAQ', link: '/faq/'},
                    {text: '隐私政策', link: '/privacy/'},
                    {text: '开发计划', link: '/todo/'},
                ]
            }
        ],
        lastUpdated: true,
        // 假定是 GitHub. 同时也可以是一个完整的 GitLab URL
        repo: 'imoyao/fundmate',
        // 假如文档不是放在仓库的根目录下：
        docsDir: 'docs',
        // 假如文档放在一个特定的分支下：
        docsBranch: 'docs',
        // 默认是 false, 设置为 true 来启用
        editLinks: true
    }
}