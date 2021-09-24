---
title: 粮草先动| 环境安装
---
## 版本信息
我们不会给出每一种软件的详细安装步骤，只会附上参考链接和软件安装完成的版本信息。具体如下：
- MySQL
```bash
mysql --version
# mysql  Ver 14.14 Distrib 5.7.32, for Linux (x86_64) using  EditLine wrapper
```
- Python3
```bash
python3 --version
# Python 3.7.5
```
参阅[Centos7 安装 Python3.7 详细教程](https://blog.csdn.net/xuezhangjun0121/article/details/103903984)

- c++编译环境
```bash
yum install gcc gcc-c++
```

## 前端
- nvm（可选）
用以控制不同的 node 版本（本机可能有多个项目，使用的 node 版本不同），我们主要使用 Windows 版本——[coreybutler/nvm-windows: A node.js version management utility for Windows. Ironically written in Go.](https://github.com/coreybutler/nvm-windows)
使用参考此处：[使用 nvm 管理不同版本的 node 与 npm | 菜鸟教程](https://www.runoob.com/w3cnote/nvm-manager-node-versions.html)
- nodejs
```bash
node --version
v12.2.0
```
注意：如果 npm 不可用，请参考[window 系统下使用 nvm 安装后 node 生效但是 npm 不生效_益达木咸醇的博客-CSDN 博客](https://blog.csdn.net/weixin_45766506/article/details/106726679) 修复，node 对应 npm 版本参照：[以往的版本 | Node.js](https://nodejs.org/zh-cn/download/releases/)，npm 下载镜像：[NPM Mirror](https://npm.taobao.org/mirrors/npm/)
- yarn
```bash
npm install yarn
```
```plain
yarn install
```
::: warning 如果遇到提示`node-gyp` 安装错误
```plain
yarn global add node-gyp
# 以管理员身份运行powershell或者cmd执行以下指令
npm install --global windows-build-tools
```
参阅：
1. [在 windows 下安装 node-gyp - 简书](https://www.jianshu.com/p/d075d8aad305/)
2. [node.js - How can I solve error gypgyp ERR!ERR! find VSfind VS msvs_version not set from command line or npm config? - Stack Overflow](https://stackoverflow.com/questions/57879150/how-can-i-solve-error-gypgyp-errerr-find-vsfind-vs-msvs-version-not-set-from-c)
:::