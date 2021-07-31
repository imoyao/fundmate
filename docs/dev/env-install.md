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
- nodejs
```bash
node --version
v12.2.0
```
- yarn
```bash
npm install yarn
```
```
yarn install
```
::: warning 如果遇到提示`node-gyp` 安装错误
```
yarn global add node-gyp
# 以管理员身份运行powershell或者cmd执行以下指令
npm install --global windows-build-tools
```
参阅：
1. [在windows下安装node-gyp - 简书](https://www.jianshu.com/p/d075d8aad305/)
2. [node.js - How can I solve error gypgyp ERR!ERR! find VSfind VS msvs_version not set from command line or npm config? - Stack Overflow](https://stackoverflow.com/questions/57879150/how-can-i-solve-error-gypgyp-errerr-find-vsfind-vs-msvs-version-not-set-from-c)
:::