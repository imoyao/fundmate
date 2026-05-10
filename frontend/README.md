<h1>vue-pure-admin精简版（非国际化版本）</h1>

[![license](https://img.shields.io/github/license/pure-admin/vue-pure-admin.svg)](LICENSE)

**中文** | [English](./README.en-US.md)

## 介绍

精简版是基于 [vue-pure-admin](https://github.com/pure-admin/vue-pure-admin) 提炼出的架子，包含主体功能，更适合实际项目开发，打包后的大小在全局引入 [element-plus](https://element-plus.org) 的情况下仍然低于 `2.3MB`，并且会永久同步完整版的代码。开启 `brotli` 压缩和 `cdn` 替换本地库模式后，打包大小低于 `350kb`

## 版本选择

当前是非国际化版本，如果您需要国际化版本 [请点击](https://github.com/pure-admin/pure-admin-thin/tree/i18n)

## 配套视频

[点我查看 UI 设计](https://www.bilibili.com/video/BV17g411T7rq)
[点我查看快速开发教程](https://www.bilibili.com/video/BV1kg411v7QT)

## 配套保姆级文档

[点我查看 vue-pure-admin 文档](https://pure-admin.cn/)
[点我查看 @pureadmin/utils 文档](https://pure-admin-utils.netlify.app)

## 高级服务

[点我查看详情](https://pure-admin.cn/pages/service/)

## 预览

[查看预览](https://pure-admin-thin.netlify.app/#/login)

## 维护者

[xiaoxian521](https://github.com/xiaoxian521)

## ⚠️ 注意

精简版不接受任何 `issues` 和 `pr`，如果有问题请到完整版 [issues](https://github.com/pure-admin/vue-pure-admin/issues/new/choose) 去提，谢谢！

## 许可证

[MIT © 2020-present, pure-admin](./LICENSE)

```
showbuy
├─ 📁.husky
│  ├─ 📁_
│  │  ├─ 📄.gitignore
│  │  ├─ 📄applypatch-msg
│  │  ├─ 📄commit-msg
│  │  ├─ 📄h
│  │  ├─ 📄husky.sh
│  │  ├─ 📄post-applypatch
│  │  ├─ 📄post-checkout
│  │  ├─ 📄post-commit
│  │  ├─ 📄post-merge
│  │  ├─ 📄post-rewrite
│  │  ├─ 📄pre-applypatch
│  │  ├─ 📄pre-auto-gc
│  │  ├─ 📄pre-commit
│  │  ├─ 📄pre-merge-commit
│  │  ├─ 📄pre-push
│  │  ├─ 📄pre-rebase
│  │  └─ 📄prepare-commit-msg
│  ├─ 📄commit-msg
│  ├─ 📄common.sh
│  └─ 📄pre-commit
├─ 📁.vscode
│  ├─ 📄extensions.json
│  ├─ 📄settings.json
│  ├─ 📄vue3.0.code-snippets
│  ├─ 📄vue3.2.code-snippets
│  └─ 📄vue3.3.code-snippets
├─ 📁build
│  ├─ 📄cdn.ts
│  ├─ 📄compress.ts
│  ├─ 📄info.ts
│  ├─ 📄optimize.ts
│  ├─ 📄plugins.ts
│  └─ 📄utils.ts
├─ 📁mock
│  ├─ 📄asyncRoutes.ts
│  ├─ 📄login.ts
│  └─ 📄refreshToken.ts
├─ 📁public
│  ├─ 📄favicon.ico
│  ├─ 📄logo.svg
│  └─ 📄platform-config.json
├─ 📁src
│  ├─ 📁api
│  │  ├─ 📄routes.ts
│  │  └─ 📄user.ts
│  ├─ 📁assets
│  │  ├─ 📁iconfont
│  │  │  ├─ 📄iconfont.css
│  │  │  ├─ 📄iconfont.js
│  │  │  ├─ 📄iconfont.json
│  │  │  ├─ 📄iconfont.ttf
│  │  │  ├─ 📄iconfont.woff
│  │  │  └─ 📄iconfont.woff2
│  │  ├─ 📁login
│  │  │  ├─ 📄avatar.svg
│  │  │  ├─ 📄bg.png
│  │  │  └─ 📄illustration.svg
│  │  ├─ 📁status
│  │  │  ├─ 📄403.svg
│  │  │  ├─ 📄404.svg
│  │  │  └─ 📄500.svg
│  │  ├─ 📁svg
│  │  │  ├─ 📄back_top.svg
│  │  │  ├─ 📄dark.svg
│  │  │  ├─ 📄day.svg
│  │  │  ├─ 📄enter_outlined.svg
│  │  │  ├─ 📄exit_screen.svg
│  │  │  ├─ 📄full_screen.svg
│  │  │  ├─ 📄keyboard_esc.svg
│  │  │  └─ 📄system.svg
│  │  ├─ 📁table-bar
│  │  │  ├─ 📄collapse.svg
│  │  │  ├─ 📄drag.svg
│  │  │  ├─ 📄expand.svg
│  │  │  ├─ 📄refresh.svg
│  │  │  └─ 📄settings.svg
│  │  └─ 📄user.jpg
│  ├─ 📁components
│  │  ├─ 📁ReAuth
│  │  │  ├─ 📁src
│  │  │  │  └─ 📄auth.tsx
│  │  │  └─ 📄index.ts
│  │  ├─ 📁ReCol
│  │  │  └─ 📄index.ts
│  │  ├─ 📁ReDialog
│  │  │  ├─ 📄index.ts
│  │  │  ├─ 📄index.vue
│  │  │  └─ 📄type.ts
│  │  ├─ 📁ReIcon
│  │  │  ├─ 📁src
│  │  │  │  ├─ 📄hooks.ts
│  │  │  │  ├─ 📄iconfont.ts
│  │  │  │  ├─ 📄iconifyIconOffline.ts
│  │  │  │  ├─ 📄iconifyIconOnline.ts
│  │  │  │  ├─ 📄offlineIcon.ts
│  │  │  │  └─ 📄types.ts
│  │  │  └─ 📄index.ts
│  │  ├─ 📁RePerms
│  │  │  ├─ 📁src
│  │  │  │  └─ 📄perms.tsx
│  │  │  └─ 📄index.ts
│  │  ├─ 📁RePureTableBar
│  │  │  ├─ 📁src
│  │  │  │  └─ 📄bar.tsx
│  │  │  └─ 📄index.ts
│  │  ├─ 📁ReSegmented
│  │  │  ├─ 📁src
│  │  │  │  ├─ 📄index.css
│  │  │  │  ├─ 📄index.tsx
│  │  │  │  └─ 📄type.ts
│  │  │  └─ 📄index.ts
│  │  └─ 📁ReText
│  │     ├─ 📁src
│  │     │  └─ 📄index.vue
│  │     └─ 📄index.ts
│  ├─ 📁config
│  │  └─ 📄index.ts
│  ├─ 📁directives
│  │  ├─ 📁auth
│  │  │  └─ 📄index.ts
│  │  ├─ 📁copy
│  │  │  └─ 📄index.ts
│  │  ├─ 📁longpress
│  │  │  └─ 📄index.ts
│  │  ├─ 📁optimize
│  │  │  └─ 📄index.ts
│  │  ├─ 📁perms
│  │  │  └─ 📄index.ts
│  │  ├─ 📁ripple
│  │  │  ├─ 📄index.scss
│  │  │  └─ 📄index.ts
│  │  └─ 📄index.ts
│  ├─ 📁layout
│  │  ├─ 📁components
│  │  │  ├─ 📁lay-content
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁lay-footer
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁lay-frame
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁lay-navbar
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁lay-notice
│  │  │  │  ├─ 📁components
│  │  │  │  │  ├─ 📄NoticeItem.vue
│  │  │  │  │  └─ 📄NoticeList.vue
│  │  │  │  ├─ 📄data.ts
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁lay-panel
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁lay-search
│  │  │  │  ├─ 📁components
│  │  │  │  │  ├─ 📄SearchFooter.vue
│  │  │  │  │  ├─ 📄SearchHistory.vue
│  │  │  │  │  ├─ 📄SearchHistoryItem.vue
│  │  │  │  │  ├─ 📄SearchModal.vue
│  │  │  │  │  └─ 📄SearchResult.vue
│  │  │  │  ├─ 📄index.vue
│  │  │  │  └─ 📄types.ts
│  │  │  ├─ 📁lay-setting
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁lay-sidebar
│  │  │  │  ├─ 📁components
│  │  │  │  │  ├─ 📄SidebarBreadCrumb.vue
│  │  │  │  │  ├─ 📄SidebarCenterCollapse.vue
│  │  │  │  │  ├─ 📄SidebarExtraIcon.vue
│  │  │  │  │  ├─ 📄SidebarFullScreen.vue
│  │  │  │  │  ├─ 📄SidebarItem.vue
│  │  │  │  │  ├─ 📄SidebarLeftCollapse.vue
│  │  │  │  │  ├─ 📄SidebarLinkItem.vue
│  │  │  │  │  ├─ 📄SidebarLogo.vue
│  │  │  │  │  └─ 📄SidebarTopCollapse.vue
│  │  │  │  ├─ 📄NavHorizontal.vue
│  │  │  │  ├─ 📄NavMix.vue
│  │  │  │  └─ 📄NavVertical.vue
│  │  │  └─ 📁lay-tag
│  │  │     ├─ 📁components
│  │  │     │  └─ 📄TagChrome.vue
│  │  │     ├─ 📄index.scss
│  │  │     └─ 📄index.vue
│  │  ├─ 📁hooks
│  │  │  ├─ 📄useBoolean.ts
│  │  │  ├─ 📄useDataThemeChange.ts
│  │  │  ├─ 📄useLayout.ts
│  │  │  ├─ 📄useMultiFrame.ts
│  │  │  ├─ 📄useNav.ts
│  │  │  └─ 📄useTag.ts
│  │  ├─ 📄frame.vue
│  │  ├─ 📄index.vue
│  │  ├─ 📄redirect.vue
│  │  └─ 📄types.ts
│  ├─ 📁plugins
│  │  ├─ 📄echarts.ts
│  │  └─ 📄elementPlus.ts
│  ├─ 📁router
│  │  ├─ 📁modules
│  │  │  ├─ 📄account.ts
│  │  │  ├─ 📄asset.ts
│  │  │  ├─ 📄error.ts
│  │  │  ├─ 📄home.ts
│  │  │  ├─ 📄remaining.ts
│  │  │  └─ 📄system.ts
│  │  ├─ 📄index.ts
│  │  └─ 📄utils.ts
│  ├─ 📁store
│  │  ├─ 📁modules
│  │  │  ├─ 📄app.ts
│  │  │  ├─ 📄epTheme.ts
│  │  │  ├─ 📄multiTags.ts
│  │  │  ├─ 📄permission.ts
│  │  │  ├─ 📄settings.ts
│  │  │  └─ 📄user.ts
│  │  ├─ 📄index.ts
│  │  ├─ 📄types.ts
│  │  └─ 📄utils.ts
│  ├─ 📁style
│  │  ├─ 📄dark.scss
│  │  ├─ 📄element-plus.scss
│  │  ├─ 📄index.scss
│  │  ├─ 📄login.css
│  │  ├─ 📄reset.scss
│  │  ├─ 📄sidebar.scss
│  │  ├─ 📄tailwind.css
│  │  ├─ 📄theme.scss
│  │  └─ 📄transition.scss
│  ├─ 📁utils
│  │  ├─ 📁http
│  │  │  ├─ 📄index.ts
│  │  │  └─ 📄types.d.ts
│  │  ├─ 📁localforage
│  │  │  ├─ 📄index.ts
│  │  │  └─ 📄types.d.ts
│  │  ├─ 📁progress
│  │  │  └─ 📄index.ts
│  │  ├─ 📄auth.ts
│  │  ├─ 📄globalPolyfills.ts
│  │  ├─ 📄message.ts
│  │  ├─ 📄mitt.ts
│  │  ├─ 📄preventDefault.ts
│  │  ├─ 📄print.ts
│  │  ├─ 📄propTypes.ts
│  │  ├─ 📄responsive.ts
│  │  ├─ 📄sso.ts
│  │  └─ 📄tree.ts
│  ├─ 📁views
│  │  ├─ 📁account
│  │  │  ├─ 📁components
│  │  │  │  ├─ 📄AccountInfoSection.vue
│  │  │  │  ├─ 📄AssetCard.vue
│  │  │  │  ├─ 📄AssetDistributionChart.vue
│  │  │  │  ├─ 📄ProfitTrendChart.vue
│  │  │  │  └─ 📄TransactionTable.vue
│  │  │  ├─ 📄AccountDetail.vue
│  │  │  ├─ 📄AccountManagement.vue
│  │  │  ├─ 📄AccountOverview.vue
│  │  │  ├─ 📄AssetManagement.vue
│  │  │  ├─ 📄InvestmentAnalysis.vue
│  │  │  ├─ 📄Overview.vue
│  │  │  └─ 📄TransactionTable.vue
│  │  ├─ 📁asset
│  │  │  ├─ 📁bank
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁funds
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁precious
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁realestate
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁stocks
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📄AssetDetail.vue
│  │  │  ├─ 📄AssetOverview.vue
│  │  │  ├─ 📄Assets.vue
│  │  │  ├─ 📄IntelligentAnalysis.vue
│  │  │  └─ 📄Overview.vue
│  │  ├─ 📁error
│  │  │  ├─ 📄403.vue
│  │  │  ├─ 📄404.vue
│  │  │  └─ 📄500.vue
│  │  ├─ 📁exchange
│  │  │  ├─ 📁account
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁asset
│  │  │  │  └─ 📄index.vue
│  │  │  └─ 📁Record
│  │  │     ├─ 📁components
│  │  │     │  ├─ 📄Step1.vue
│  │  │     │  ├─ 📄Step2.vue
│  │  │     │  └─ 📄Step3.vue
│  │  │     └─ 📄index.vue
│  │  ├─ 📁login
│  │  │  ├─ 📁utils
│  │  │  │  ├─ 📄motion.ts
│  │  │  │  ├─ 📄rule.ts
│  │  │  │  └─ 📄static.ts
│  │  │  └─ 📄index.vue
│  │  ├─ 📁permission
│  │  │  ├─ 📁button
│  │  │  │  ├─ 📄index.vue
│  │  │  │  └─ 📄perms.vue
│  │  │  └─ 📁page
│  │  │     └─ 📄index.vue
│  │  ├─ 📁system
│  │  │  └─ 📄SystemSettings.vue
│  │  └─ 📁welcome
│  │     └─ 📄index.vue
│  ├─ 📄App.vue
│  └─ 📄main.ts
├─ 📁types
│  ├─ 📄directives.d.ts
│  ├─ 📄global-components.d.ts
│  ├─ 📄global.d.ts
│  ├─ 📄index.d.ts
│  ├─ 📄router.d.ts
│  ├─ 📄shims-tsx.d.ts
│  └─ 📄shims-vue.d.ts
├─ 📄.browserslistrc
├─ 📄.dockerignore
├─ 📄.editorconfig
├─ 📄.env
├─ 📄.env.development
├─ 📄.env.production
├─ 📄.env.staging
├─ 📄.gitignore
├─ 📄.lintstagedrc
├─ 📄.markdownlint.json
├─ 📄.npmrc
├─ 📄.nvmrc
├─ 📄.prettierrc.js
├─ 📄.stylelintignore
├─ 📄commitlint.config.js
├─ 📄Dockerfile
├─ 📄eslint.config.js
├─ 📄foo.html
├─ 📄index.html
├─ 📄index2.html
├─ 📄LICENSE
├─ 📄package.json
├─ 📄pnpm-lock.yaml
├─ 📄postcss.config.js
├─ 📄README.en-US.md
├─ 📄README.md
├─ 📄SKILL.md
├─ 📄stylelint.config.js
├─ 📄tsconfig.json
└─ 📄vite.config.ts
```
