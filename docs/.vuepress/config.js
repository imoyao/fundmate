module.exports = {
  title: '基伴',
  description: '基金理财好伙伴！',
  // theme: 'antdocs',
  // 释出目录
  dest: 'docs/public',
  themeConfig: {
    sidebar: [
      ['/', '简介'],
      ['/user','使用'],
      ['/dev','开发'],
      ['/guide','部署'],
      ['/api','接口'],
      '/link'
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