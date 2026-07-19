module.exports = {
    title: '叽咕',
    description: '基金理财好伙伴！',
    theme: 'antdocs',
    // 释出目录
    dest: 'docs/public',
    plugins: {
        "vuepress-plugin-auto-sidebar": {},
         "md-enhance":
          {
            // 启用脚注
            footnote: true
          }
    },
    themeConfig: {
        nav: [
            {text: '首页', link: '/'},
            {text: '使用', link: '/guide/'},
            {text: '开发', link: '/dev/'},
            {text: '接口', link: '/api/'},
            {text: '测试', link: '/pytest/'},
            {text: '关于', link: '/about/'},
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
