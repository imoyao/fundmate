---
title: Python 项目的目录结构问题
---

## 为什么需要结构化

> 对于一个计划长期维护的项目而言，代码风格、API 设计和自动化是非常关键的。同样的，对于工程的架构,仓库的结构也是关键的一部分。

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
本文中以`openstack-neutron`版本为例，且根据 github 上的源码来看，最新版的代码结构与文中展示也有很大差异。而下文的更加合理，结构化。
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

### 使用 cookiecutter 生成项目目录

1. 进入虚拟环境
```bash
source venv/bin/activate
```
2. 安装 cookiecutter
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
│  ├── base.py
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
│  ├── base.py
│  └── webpack
├── LICENSE
├── package.json
├── pyproject.toml
├── README.md
├── requirements
│  ├── dev.txt
├── requirements.txt
├── setup.cfg
├── shell_scripts
│  ├── auto_pipenv.sh
│  └── supervisord_entrypoint.sh
├── supervisord.conf
├── supervisord_programs
│  └── gunicorn.conf
├── tests
│  ├── test_conf.py
│  ├── factories.py
│  ├── __init__.py
│  ├── settings.py
│  ├── test_forms.py
│  ├── test_functional.py
│  └── test_models.py
└── webpack.config.js

```

如果项目中前端页面使用模板语言编写，那么我们只需要在此基础上继续编写代码即可；而因为我们的项目是前后端分离的，所以需要将目录中的 html 文件都删掉。

### 删除无用（可选）
将目录下的 html、static 文件全部删除，最终目录结构如下：
```bash

├── autoapp.py
├── db
│     └── ……
├── dev.db
├── docker-compose.yml
├── Dockerfile
├── fmt
│     ├── ……
│     └── ……
├── fundmate
│     ├── base.py
│     ├── commands.py
│     ├── compat.py
│     ├── database.py
│     ├── extensions.py
│     ├── __init__.py
│     ├── libcommon
│     ├── public
│     ├── settings.py
│     ├── user
│     └── base.py
├── __init__.py
├── LICENSE
├── pyproject.toml
├── README.md
├── requirements
│     ├── dev.txt
├── requirements.txt
├── setup.cfg
├── shell_scripts
│     └── ……
├── supervisord.conf
├── supervisord_programs
│     └── gunicorn.conf
└── tests
|    |__……

```

### 启动应用

```bash
(fmp) [root@localhost backend]# flask run
 * Serving Flask app "autoapp.py" (lazy loading)
 * Environment: development
 * Debug mode: on
 * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)     # 注意此行
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: 323-729-374

```
:::warning

1. 以这种方式启动的程序（使用默认 host`127.0.0.1`），只能通过本机访问。因为我们的服务是跑在虚拟机上的，所以直接访问或报“无法访问此页面”，我们需要通过设置环境变量或者使用显式指定参数`--host`的方式配置访问的 host 为`0.0.0.0`，意为指定监听在本机的所有 IP 地址，这样内网就可以直接访问了。当然你也可以使用`--port`指定访问的端口。
```bash
flask run --port=8000
```
更多参阅：[Command Line Interface — Flask Documentation (1.1.x)](https://flask.palletsprojects.com/en/1.1.x/cli/)

2. 内置的开发服务器只能用于开发时使用，部署上线的时候要换用性能更好的`web`服务器如 nginx。
:::

```bash
^C(fmp) [root@localhost backend]# flask run --host 0.0.0.0
 * Serving Flask app "autoapp.py" (lazy loading)
 * Environment: development
 * Debug mode: on
 * Running on http://0.0.0.0:5000/ (Press CTRL+C to quit)
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: 323-729-374
```
最终，我们看到界面显示出我们的首页内容。

![](https://cdn.jsdelivr.net/gh/masantu/statics/images/20210117120554.png)

#### 自动发现程序实例

一般来说，在执行`flask run`命令运行程序前，我们需要提供程序实例所在模块的位置。我们在上面可以直接运行程序，是因为 Flask 会自动探测程序实例。

> 旧的启动开发服务器的方式是在代码中调用`app.run()`方法，然后程序执行`python app.py`（指定你的入口文件），目前已不推荐使用（deprecated）。

自动探测存在下面这些规则：

*   从当前目录寻找`app.py`和`wsgi.py`模块，并从中寻找名为`app`或`application`的程序实例。
*   从环境变量`FLASK_APP`对应的模块名/导入路径寻找名为`app`或`application`的程序实例。如果 你的程序主模块是其他名称，比如 `hello.py`，那么需要设置环境变量`FLASK_APP`，将包含程序 实例的模块名赋值给这个变量。

Linux 或 macOS 系统使用 export 命令：
```plain
  $ export FLASK_APP= hello
```
在 Windows 系统 中 使用 set 命令：
```plain
 > set FLASK_APP= hello
```

:::tip
注意：由于我们删除了所有的模板文件，所以需要将代码中的`render_template`都暂时修改为`return {{ sth }}`，即返回字符串。
```python

@blueprint.route("/", methods=["GET", "POST"])
def home():
    """Home page."""
    form = LoginForm(request.form)
    current_app.logger.info("Hello from the home page!")
    # Handle logging in
    if request.method == "POST":
        if form.validate_on_submit():
            login_user(form.user)
            flash("You are logged in.", "success")
            redirect_url = request.args.get("next") or url_for("user.members")
            return redirect(redirect_url)
        else:
            flash_errors(form)
    return 'Hello,Flask!'
```
:::

### 按业务组织

一个大型项目中，会包含很多子业务，比如本项目中我们会有用户管理、基金管理、流水记录等，每一部分都可以是独立的项目，在 Flask 中，按照业务的方式将文件划分开，就是按业务方式来组织项目结构，这样的组织方式有助于并行开发和分而治之。

## 相关链接
- [Packaging Python Projects — Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
- [python - Separation of business logic and data access in django - Stack Overflow](https://stackoverflow.com/questions/12578908/separation-of-business-logic-and-data-access-in-django)
- [项目布局 — Flask 中文文档（ 1.1.1 ）](https://dormousehole.readthedocs.io/en/latest/tutorial/layout.html)
- [结构化您的工程 — The Hitchhiker's Guide to Python](https://pythonguidecn.readthedocs.io/zh/latest/writing/structure.html)
- [使用 cookiecutter-flask 快速生成 python 后端项目 - 知乎](https://zhuanlan.zhihu.com/p/25874886)
- [第 125 天：Flask 项目结构 | Python 技术](http://www.justdopython.com/2020/01/18/python-web-flask-project-125/)
- [cookiecutter-flask 使用笔记_代码就是生产力！-CSDN 博客](https://blog.csdn.net/yannanxiu/article/details/68059532)
- [Flask 项目结构分享 | Python 技术论坛](https://learnku.com/python/t/38740)
- [一个比较好的 flask 项目目录结构_bocai_xiaodaidai 的博客-CSDN 博客_flask 项目目录结构](https://blog.csdn.net/bocai_xiaodaidai/article/details/101527678)
- [Flask RESTful API 开发 更好的项目结构 - 简书](https://www.jianshu.com/p/beb4763f385c)
- [我们的 Tornado 项目结构 | the5fire](https://www.the5fire.com/966.html)
