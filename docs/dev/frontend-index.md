---
title: 开始
---

## 前端模板

最终选择：[Armour/vue-typescript-admin-template: 🖖 A vue-cli 3.0 + typescript minimal admin template](https://github.com/Armour/vue-typescript-admin-template)

理由：TS+vue-element-admin 的可持续借鉴

~~[chuzhixin/vue-admin-beautiful](https://github.com/chuzhixin/vue-admin-beautiful)~~

作者只推广，项目没有 issues

[PanJiaChen/vue-element-admin](https://github.com/PanJiaChen/vue-element-admin/)

[hooray/fantastic-admin](https://github.com/hooray/fantastic-admin)

## 安装最简版本
本项目目标是进行二次开发。所以使用位于 minimal 分支的简易基础模版。

::: danger
运行`yarn install`报错`node-gyp exited with code: 1`，参考[nodejs/node-gyp: Node.js native addon build tool](https://github.com/nodejs/node-gyp#on-windows)处理

1. 安装  Visual Studio installation
安装前请确保Windows C盘有4G+存储空间，否则可能安装失败，如果不满足，请参考：[C盘快满了，该如何清理？ - 知乎](https://www.zhihu.com/question/27608145)
```bash
npm install --global --production windows-build-tools
```
:::

::: warning
如果还是报错请确认使用`CMD`安装，本人`Terminus`报错，使用 CMD通过
:::

![成功标志](https://cdn.jsdelivr.net/gh/masantu/statics/images/Snipaste_2020-12-30_00-02-53.png)

2. 启动项目
```bash
yarn install
yarn serve
```
![](https://cdn.jsdelivr.net/gh/masantu/statics/images/20201230001135.png)

3. 安装调试工具
安装[Vue.js devtools](https://chrome.google.com/webstore/detail/vuejs-devtools/nhdogjmejiglipccpnnnanhbledajbpd)便于调试

## 设计

以理财通为原型，以支付宝为模板，