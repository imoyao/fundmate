---
title: 粮草先动| 环境安装
---

## 版本信息

我们不会给出每一种软件的详细安装步骤，只会附上参考链接和软件安装完成的版本信息。具体如下：

- MySQL

```bash
mysql --version
# mysql  Ver 14.14 Distrib 8.0.27, for Linux (x86_64) using  EditLine wrapper
```

- Python3

```bash
python3 --version
# Python 3.7.5
```

参阅[Centos7 安装 Python3.7 详细教程](https://blog.csdn.net/xuezhangjun0121/article/details/103903984)

::: warning
针对`ModuleNotFoundError: No module named '_ctypes'`错误：

```shell
yum -y install zlib-devel bzip2-devel openssl-devel ncurses-devel sqlite-devel readline-devel tk-devel gdbm-devel db4-devel libpcap-devel xz-devel
```

:::

- c++编译环境

```bash
yum install gcc gcc-c++
```

## 前端

- nvm（可选）
  用以控制不同的 node 版本（本机可能有多个项目，使用的 node 版本不同），我们主要使用 Windows 版本——[coreybutler/nvm-windows: A node.js version management utility for Windows. Ironically written in Go.](https://github.com/coreybutler/nvm-windows)
  使用参考此处：[使用 nvm 管理不同版本的 node 与 npm | 菜鸟教程](https://www.runoob.com/w3cnote/nvm-manager-node-versions.html)
  临时换源：
  1. Linux

```shell
export NVM_NODEJS_ORG_MIRROR=https://npm.taobao.org/mirrors/node/
```

  2. Windows
  在 nvm 的安装路径下，找到 settings.txt，在后面加上这两行

```shell
node_mirror: https://npm.taobao.org/mirrors/node/
npm_mirror: https://npm.taobao.org/mirrors/npm/
```

  之后重启终端。

- nodejs

```bash
node --version
v12.2.0
```

注意：如果 npm 不可用，请参考[window 系统下使用 nvm 安装后 node 生效但是 npm 不生效_益达木咸醇的博客-CSDN 博客](https://blog.csdn.net/weixin_45766506/article/details/106726679) 修复，node 对应 npm 版本参照：[以往的版本 | Node.js](https://nodejs.org/zh-cn/download/releases/)，npm 下载镜像：[NPM Mirror](https://npm.taobao.org/mirrors/npm/)

- yarn

国内镜像加速

```shell
npm config set registry https://registry.npmmirror.com
```

下载 yarn

```bash
npm install yarn
```

```shell
SASS_BINARY_SITE=http://npm.taobao.org/mirrors/node-sass yarn
```

在 yarn 命令前添加 `SASS_BINARY_SITE=http://npm.taobao.org/mirrors/node-sass` 的目的是告诉 yarn 到淘宝的镜像去下载 node-sass 二进制文件。

```bash
yarn install
```

::: warning 如果遇到提示`node-gyp` 安装错误

```plain
yarn global add node-gyp
# 以管理员身份运行powershell或者cmd执行以下指令
npm install --global windows-build-tools
```

:::

参阅：

1. [在 windows 下安装 node-gyp - 简书](https://www.jianshu.com/p/d075d8aad305/)
2. [node.js - How can I solve error gypgyp ERR!ERR! find VSfind VS msvs_version not set from command line or npm config? - Stack Overflow](https://stackoverflow.com/questions/57879150/how-can-i-solve-error-gypgyp-errerr-find-vsfind-vs-msvs-version-not-set-from-c)
::::

## 虚拟环境与项目准备

### 使用虚拟环境

使用 venv 进行 python 版本环境切换：

```bash
cd backend
python3 -m venv fmp   # {ENV_NAME} 本文中以 fmp 为例
source fmp/bin/activate
```

### 包管理

使用 pip 进行包管理。

### 配置控制

在大多数教程中，至少 99% 会提到：你的项目在哪个环境下工作——开发、调试还是生产？这是需要提前做的一个设置。花点时间了解如何管理配置，对于部署至关重要。

### 路由和蓝图

前端访问的 API 名称和我们的路由应该是一一对应的。

相关链接：

- [Beginning with a Flask project. 5 most important things to know before starting.](https://itnext.io/beginning-with-flask-project-the-5-most-important-information-to-know-before-starting-f075e0fb0aec)
- [第 1 章：准备工作 - Flask 入门教程](https://read.helloflask.com/c1-ready)
