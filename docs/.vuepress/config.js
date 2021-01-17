module.exports = {
    title: '基伴',
    description: '基金理财好伙伴！',
    theme: 'antdocs',
    // 释出目录
    dest: 'docs/public',
    plugins: {
        "vuepress-plugin-auto-sidebar": {}
    },
    themeConfig: {
        nav: [
            {text: '首页', link: '/'},
            {text: '开发', link: '/dev/'},
            {text: '部署', link: '/guide/'},
            {text: '接口', link: '/api/'},
            {text: '计划', link: '/about/'},
        ],
        sidebar: [
            '/',
            ['/todo', 'TODO']
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