---
title: 开发指南
---

## 说明

这个目录主要用于存放开发记录，帮助其他开发者理解我要做什么，以及是怎么做的。如果后期有人愿意加入进来一起开发的话，可以以该部分作为指导手册。

让开发者可以部署起来。

## 文档

基伴使用[VuePress](https://vuepress.vuejs.org/zh/)生成文档系统。

- 预览

你可以使用如下命令在本地生成预览文档：
```bash
yarn docs:dev
```
- build
```bash
yarn docs:build
```
- 更新

从 master/dev 分支合并更新
```bash
git checkout master
git pull
git checkout docs
git checkout dev docs/*  # dev为要合并的分支，docs为要合并的目录
```
- lint 文档
```bash
yarn docs:lint
```

## 预览

### 前端

```bash
cd frontend
yarn install
yarn run dev
```
