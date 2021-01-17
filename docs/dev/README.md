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
git checkout docs # 或者 git checkout master
git pull
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

### 后端
- 安装开发环境
```bash
cd backend
python3 -m venv fmp
source fmp/bin/activate 
pip install -r requirements.txt
```
- 修改环境变量`.env`
```plain
flask run --host=0.0.0.0
```
- 启动数据库
- 初始化数据库
```bash
flask init-db # 更多命令执行flask --help 查看
```

## TODO

- 使用的插件

[aaron-bond/better-comments](https://github.com/aaron-bond/better-comments)