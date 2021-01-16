---
title: Python 项目的目录结构问题
permalink: /structure 
---

## 为什么需要结构化

>  对于一个计划长期维护的项目而言，代码风格、API设计和自动化是非常关键的。同样的，对于工程的架构,仓库的结构也是关键的一部分。

回顾我们的经历的代码，看看都曾经遇到过哪些问题：

1. 随意且混乱的`import`（循环导包）和不规范的`import`（from foo import *）；
2. 大量复制-粘贴的重复代码
一段代码，可以在同一个项目中多次遇到，甚至在同一个文件中多次遇到，因为后面维护人员懒得查找前面人写的代码，所以另起炉灶，导致同一个功能可以由两个函数完成；

一段代码只有坚持维护才能保持生命力，如果由于结构不够良好使维护者丧失阅读耐心，那仿佛进入一片“鬼打墙”的森林，这样的代码离变成 [屎山](https://www.zhihu.com/question/272065178) 恐怕只是时间问题了。

## 范例

我们先看看成功的范例都是什么样子的。

### [Django](https://www.dusaiphoto.com/article/4/#django_1)

我们知道`Django`中使用 [django-admin and manage.py](https://docs.djangoproject.com/zh-hans/3.0/ref/django-admin/#startproject) 来启动一个项目。

```bash
django-admin.py startproject samplesite
```
```bash
my_blog
│  db.sqlite3
│  manage.py
│
└─my_blog
    │  settings.py
    │  urls.py
    │  wsgi.py
    └─ __init__.py
```
### [OpenStack](https://blog.csdn.net/llg8212/article/details/19990613)

::: warning
本文中以`openstack neutron`为例，且根据github上的源码来看，最新版的代码结构与文中展示也有很大差异。而下文的更加合理，结构化。
:::

```bash
|--agent：部署在Network Node上。为整个网络提供公共服务，包括如：l3-agent（实现3层网络路由的配置），dhcp-agent（提供dhcp服务）。

|--api：对外提供RestAPI访问。在neutron-server服务中提供。

|--cmd：用于发出哪些network,subnet,port,router,floatingip已经存在

|--common：neutron模块的公共

|--db：数据库

|--debug：用于测试neutron功能

|--extensions：neutron的扩展模块，如：vpnaas，l3，lbaas等

|--locale：多语言支持

|--openstack：openstack的公共模块，来源于olso-incubator

|--plugin：实现网络功能的插件。如：linuxbridge，ml2

    |--agent：部署在Compute Node节点（真正干活的）。使vm能通过网络通信，如openvswitch中的agent是通过ovs-ofctl命令修改流规则。

|--scheduler：neutron的调度模块，负载均衡功能时使用。包含：dhcp-agent和l3-agent调度

|--server：启动NeutronApiService服务

|--service：

|--tests:
```
### [flasky](https://github.com/miguelgrinberg/flasky)

```bash
├── app
│     ├── api
│     ├── auth
│     ├── decorators.py
│     ├── email.py
│     ├── exceptions.py
│     ├── fake.py
│     ├── __init__.py
│     ├── main
│     ├── models.py
│     ├── static
│     └── templates
├── boot.sh
├── config.py
├── docker-compose.yml
├── Dockerfile
├── flasky.py
├── LICENSE
├── migrations
│     ├── alembic.ini
│     ├── env.py
│     ├── README
│     ├── script.py.mako
│     └── versions
├── Procfile
├── README.md
├── requirements
│     ├── common.txt
│     ├── dev.txt
│     ├── docker.txt
│     ├── heroku.txt
│     └── prod.txt
├── requirements.txt
└── tests
    ├── __init__.py
    ├── test_api.py
    ├── test_basics.py
    ├── test_client.py
    ├── test_selenium.py
    └── test_user_model.py
```

## 如何实现

### 使用cookiecutter生成项目目录

1. 进入虚拟环境
```bash
source fmp/bin/activate
```
2. 安装cookiecutter
```bash
pip install cookiecutter
cookiecutter https://github.com/sloria/cookiecutter-flask.git
```
3. 输入相关信息生成项目结构
```bash
(fmp) [root@localhost fundmate]# tree -L 3
.
├── assets
│  ├── css
│  │  └── style.css
│  ├── img
│  │  └── favicon.ico
│  └── js
│      ├── main.js
│      ├── plugins.js
│      └── script.js
├── autoapp.py
├── dev.db
├── docker-compose.yml
├── Dockerfile
├── fundmate
│  ├── app.py
│  ├── commands.py
│  ├── compat.py
│  ├── database.py
│  ├── extensions.py
│  ├── __init__.py
│  ├── public
│  │  ├── forms.py
│  │  ├── __init__.py
│  │  └── views.py
│  ├── settings.py
│  ├── static
│  │  └── build
│  ├── templates
│  │  ├── 401.html
│  │  ├── 404.html
│  │  ├── 500.html
│  │  ├── footer.html
│  │  ├── layout.html
│  │  ├── nav.html
│  │  ├── public
│  │  └── users
│  ├── user
│  │  ├── forms.py
│  │  ├── __init__.py
│  │  ├── models.py
│  │  └── views.py
│  ├── utils.py
│  └── webpack
├── LICENSE
├── package.json
├── pyproject.toml
├── README.md
├── requirements
│  ├── dev.txt
│  └── prod.txt
├── requirements.txt
├── setup.cfg
├── shell_scripts
│  ├── auto_pipenv.sh
│  └── supervisord_entrypoint.sh
├── supervisord.conf
├── supervisord_programs
│  └── gunicorn.conf
├── tests
│  ├── conftest.py
│  ├── factories.py
│  ├── __init__.py
│  ├── settings.py
│  ├── test_forms.py
│  ├── test_functional.py
│  └── test_models.py
└── webpack.config.js

```

如果前端页面使用模板语言编写，那么我们只需要在此基础上继续编写代码即可；而因为我们的项目是前后端分离的，所以需要将目录中的html文件都删掉。
### 删除无用

## 相关链接
- [结构化您的工程 — The Hitchhiker's Guide to Python](https://pythonguidecn.readthedocs.io/zh/latest/writing/structure.html)
- [使用cookiecutter-flask快速生成python后端项目 - 知乎](https://zhuanlan.zhihu.com/p/25874886)
- [第125天：Flask 项目结构 | Python技术](http://www.justdopython.com/2020/01/18/python-web-flask-project-125/)
- [cookiecutter-flask使用笔记_代码就是生产力！-CSDN博客](https://blog.csdn.net/yannanxiu/article/details/68059532)
- [Flask 项目结构分享 | Python 技术论坛](https://learnku.com/python/t/38740)
- [一个比较好的flask项目目录结构_bocai_xiaodaidai的博客-CSDN博客_flask项目目录结构](https://blog.csdn.net/bocai_xiaodaidai/article/details/101527678)
- [Flask RESTful API开发 更好的项目结构 - 简书](https://www.jianshu.com/p/beb4763f385c)
- [我们的Tornado项目结构 | the5fire](https://www.the5fire.com/966.html)
- [openstack neutron -- 概念，表结构及代码目录结构_黎林果的专栏-CSDN博客](https://blog.csdn.net/llg8212/article/details/19990613)