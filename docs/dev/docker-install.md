---
title: 使用 Docker 安装环境
---
## MySQL
- 拉取镜像
```bash
docker pull mysql:8.0.27
```
- 运行服务
```bash
docker run --name mysql8027 -e MYSQL_ROOT_PASSWORD=123456 -d -p 3307:3306 mysql:8.0.27
# 另一个更加丰富的命令（TODO:文件目录映射好像有问题，至少WSL2上会报错）
docker run -p 3306:3306 --restart=always --name mysql8027 -v /opt/docker_v/mysql/conf:/etc/mysql/conf.d  -v /data/mysql/my.cnf:/etc/mysql/my.cnf -v /data/mysql/data:/var/lib/mysql -e MYSQL_ROOT_PASSWORD=123456 -d imageID
```
::: tip
-p 3306:3306：将主机的3307端口映射到容器的3306端口
-v /opt/docker_v/mysql/conf:/etc/mysql/conf.d：将主机/opt/docker_v/mysql/conf目录挂载到容器的/etc/mysql/conf.d
-e MYSQL_ROOT_PASSWORD=123456：初始化root用户的密码
-d: 后台运行容器，并返回容器ID
imageID: 指定所使用的上一步拉取的mysql镜像ID
:::

- 进入容器
```bash
docker exec -it mysql8027 bash
```
- 停止容器
```shell
docker stop {{CONTAINER_ID}}
```

## 相关链接
- [Docker 安装 MySQL | 菜鸟教程](https://www.runoob.com/docker/docker-install-mysql.html)
- [Docker 安装 Mysql 5.7 - 叨叨软件测试 - 博客园](https://www.cnblogs.com/daodaotest/p/13172272.html)
- [Docker 创建运行多个 mysql 容器 - 小何同學 - 博客园](https://www.cnblogs.com/heyangyi/p/9288402.html)