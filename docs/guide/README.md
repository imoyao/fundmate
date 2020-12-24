---
title: 部署及其他指南
---

## 说明

让开发者可以部署起来

## 文档

基伴使用[VuePress](https://vuepress.vuejs.org/zh/)生成文档系统。
- 预览

你可以使用如下命令在本地生成预览文档：
```bash
yarn yarn docs:dev
```
- build
```bash
yarn docs:build
```
- 更新

从 master 分支合并文档
```bash
git checkout master
git pull
git checkout docs
git checkout master docs/*  
```
- lint 文档
```bash
yarn docs:lint
```