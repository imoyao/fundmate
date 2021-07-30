---
title: 使用 Docker 安装环境
---
## MySQL
- 拉去镜像
```bash
docker pull mysql:5.7
```
- 运行服务
```bash
docker run --name mysql57 -e MYSQL_ROOT_PASSWORD=123456 -d -p 3307:3306 mysql:5.7
```
- 进入容器
```bash
docker exec -it mysql57 bash
```
[Docker 安装 Mysql 5.7 - 叨叨软件测试 - 博客园](https://www.cnblogs.com/daodaotest/p/13172272.html)

[Docker 创建运行多个 mysql 容器 - 小何同學 - 博客园](https://www.cnblogs.com/heyangyi/p/9288402.html)