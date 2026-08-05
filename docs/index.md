---
layout: home

hero:
  name: 多倍贝
  text: 看见你的复利增长
  tagline: 记账即复利。多倍贝，备贝多——有备无患，自然倍多。。
  image:
    src: /logo.svg
    alt: 多倍贝
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/
    - theme: alt
      text: 关于产品
      link: /site/about

features:
  - icon: 📒
    title: 手动归集，数据在你手里
    details: 多账户、多平台买的基金，手动归集到一个账本。不接券商、不托管资金，数据始终属于你自己。
  - icon: 🔍
    title: 穿透持仓，看清底层
    details: 基金→持仓标的→标的历史估值，自动穿透。组合里到底押注了什么、风险集中在哪，一眼看清。
  - icon: 📈
    title: 算准 XIRR，别被 APP 骗了
    details: 用资金加权收益率（XIRR）还原真实收益，剔除赎回本金的干扰，看清时间价值。
  - icon: 🧭
    title: 投资温度计 · 辅助判断
    details: 估值温度计用「近 1、3、5、10 年 PE 分位」给市场热度打分，帮你避开明显过热、抓住明显低估。
  - icon: 🧩
    title: 申万一级行业 · 板块分布
    details: 持仓按申万一级行业归类，看清行业集中度，做到心中有数、手中有策。
  - icon: 🪙
    title: 开源免费 · 基础功能不收费
    details: 基础记账与账单导出长期免费。代码开源，原理透明，欢迎自行部署与审计。

featuresConfig:
  badge: 为什么选择
  title: "为什么选择 "
  subtitle: "多倍贝？"
  description: 不托管资金、不看账户密码，把数据权还给你自己

quickStart:
  badge: 三步上手
  title: "零配置 快速开始"
  subtitle: "零配置"
  description: 无需注册账号，本地即可运行

  steps:
    - step: "01"
      title: 克隆项目
      description: 从 GitHub 拉取源码到本地
      code: "git clone https://github.com/imoyao/fundmate.git && cd fundmate"
      icon: download
      color: blue
    - step: "02"
      title: 安装依赖
      description: 使用 pnpm 安装前后端依赖（后端用 PDM）
      code: |
        pnpm install
        cd backend && pdm install && cd ..
      icon: cog-6-tooth
      color: green
    - step: "03"
      title: 启动服务
      description: 分别启动文档站和后端 API 服务
      code: |
        pnpm run docs:dev       # 文档预览
        cd backend && pdm run uvicorn app.main:app --reload   # API 服务
      icon: rocket-launch
      color: purple

  helpText: 详细使用指南请参考
  helpLink: /guide/
  helpLinkText: 快速开始文档
---
