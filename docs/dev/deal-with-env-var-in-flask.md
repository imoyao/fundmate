---
title: 项目中的环境变量问题
---
## 引言

首先我们知道在平常的开发中经常需要配置一些系统**环境变量**。

再而我们在进行 web 开发的时候也会遇到各种变量的控制，比如导入开发(default)和生产环境(prod)不同的环境变量：
```bash
DEBUG=True
SECRET_KEY='abcddddd'
ALLOWED_HOSTS='*'
MAIL_USERNAME=xxxx@xx.com
MAIL_PASSWORD=abcdefg
```
本文将由浅入深地探讨这个话题，同时尝试给出一种可行的解决方案。

## 实践

### 直接 export/set

即在我们运行我们项目之前，直接利用`export`的方式导入我们需要的环境变量，比如:
```plain
# Windows
set test=123
# Linux
export test=123
```
然后在项目中使用`os`导入：

```python
# shell命令行
export test=123 # **注意这里没有空格**

# 项目中
import os
os.environ.get('test')
# 或者
os.getenv('FLASK_CONFIG', 'default')
```
如果你的应用很小或者你不会频繁切换运行环境，那么这样做没有任何问题，并且可能是一个很好的选择。但是如果尝试处理一个相对大型的工程，那么你可能每次打开新的终端会话为了设置环境变量需要执行上百条`export`语句，或者你把它写成脚本放到你的项目中去执行。如果这样，又会有数据泄露的风险。

如果你有以上的烦恼，那么不妨尝试下面的方案：

### [python-dotenv](https://github.com/theskumar/python-dotenv)

从`.env`文件中读取键值对，并将它们添加到环境变量中
```bash
# 安装包
pip install python-dotenv
# 代码开头添加如下代码段
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.

# Code of your application, which uses environment variables (e.g. from `os.environ` or
# `os.getenv`) as if they came from the actual environment.

```
官方示例参见：[theskumar/python-dotenv: Get and set values in your .env file in local and production servers.](https://github.com/theskumar/python-dotenv#getting-started)

> 当安装了`python-dotenv`时，Flask 在加载环境变量的优先级是：手动(`set/export`)设置的环境变量>`.env`中设置 的环境变量>`.flaskenv`设置的环境变量。

#### 注意事项
::: warning
1. 需要注意`.env`文件应该与程序脚本（通常为`app.py`，本项目中为`autoapp.py`）保持在同一目录等级。参阅：[不要在 Flask 程序上层目录创建 .env 和 .flaskenv 文件 - 知乎](https://zhuanlan.zhihu.com/p/128977263)
2. `python-dotenv`加载的环境变量值都是字符串类型。
:::
对于环境变量，无论是使用 `python-dotenv` 等工具写入，还是手动使用 `set` / `export` 命令，最终在 Python 里获取的时候都会是字符串类型。所以整型、浮点型和布尔类型需要转换一下。

- 解决方案

```python
# `.env`
MAIL_PORT = 465
MAIL_USE_SSL = False
MAIL_USE_TLS = True


# settings.py
class BaseConfig(object):
    ...
    MAIL_PORT = int(os.getenv('MAIL_PORT', default=587))
    MAIL_USE_SSL = True if 'true' == os.getenv('MAIL_USE_SSL') else False
    MAIL_USE_TLS = True if 'true' == os.getenv('MAIL_USE_TLS') else False
```

参阅：[用 SendGrid 发送邮件，但在邮箱中收不到邮件 - Flask Web 开发实战 - HelloFlask 论坛](https://discuss.helloflask.com/t/topic/127/3)

这是一种不那么优雅的解决办法，我们也可以使用 environs 库实现正确的类型加载，具体参见下面的章节。

##### pipenv 影响了 flask 加载`.env`环境变量

第二个坑和`pipenv`有关，众所周知 Flask 项目可以通过`.env`加载环境变量，但是，`pipenv`也可以通过`.env`加载环境变量！问题就出现了，进入`pipenv shell`虚拟环境后，修改.env 环境变量后再`flask run`启动 Flask 应用，Flask 还是用了原来的环境变量！

```bash
pipenv shell
Loading .env environment variables…
Launching subshell in virtual environment…
...
flask run  # 正常预期
# 停止flask，修改 .env 环境变量，保存
flask run  # 没达到修改变量后的预期效果
```
究其原因，是`pipenv shell`加载了环境变量并进行了缓存，然后 flask 加载环境变量时没有进行覆盖。
尤其是部署 Flask 到服务器后，以下步骤肯定有问题的！
```bash
$ pipenv shell
$ vim .env
...
$ flask run
```
- 解决方案
1. 重进`pipenv shell`
一种解决方案就是退出`pipenv shell`环境再进入：
```plain
pipenv shell
# 编辑 .env
...
exit
pipenv shell
```

2. 新建并使用`python app.py`启动

在主目录下新建一个`app.py`，拷贝下面代码，以后使用`python app.py`启动。

```python
#base.py
# coding=utf-8


import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path, override=True)  #  override=True: 覆写已存在的变量

from apps.web import create_app


app = create_app()


if __name__ == "__main__":
    app.run()
```

这种代码有时也会给一些 wsgi（比如 gunicorn）提供。

3. 设置`PIPENV_DONT_LOAD_ENV=1`

还有一个方案是设置`PIPENV_DONT_LOAD_ENV=1`，不让`pipenv`加载`.env`。

PowerShell 示例（注意没有了`Loading .env environment variables…`信息）：
```bash
$env:PIPENV_DONT_LOAD_ENV=1
pipenv shell
Launching subshell in virtual environment…
Windows PowerShell
...
```

4. 使用`.flaskenv`

`pipenv shell`不会从`.flaskenv`加载变量，所以如果有经常需要修改的环境变量也可以放在`.flaskenv`。但是我感觉一点也不优雅，因为我习惯把`.flaskenv`也提交到仓库，而留下`.env`在部署端客制化。

### 使用 [environs](https://github.com/sloria/environs) 解析配置

尽管`os.environ`对于简单的用例就足够了，但是典型的应用程序需要一种方法来处理和验证原始环境变量。 `environs`抽象了处理环境变量的常见情境。

`environs`可以：

- 将环境变量转换为正确的类型
- 指定所需的环境
- 定义默认值
- 验证环境
- 解析列表和字典值
- 解析日期，日期时间和时间增量
- 解析扩展变量
- 将配置序列化为 JSON，YAML 等。

官方示例参见：[sloria/environs: simplified environment variable parsing](https://github.com/sloria/environs#basic-usage)：

需要配置的环境变量：
```bash
export GITHUB_USER=sloria
export MAX_CONNECTIONS=100
export SHIP_DATE='1984-06-25'
export TTL=42
export ENABLE_LOGIN=true
export GITHUB_REPOS=webargs,konch,ped
export GITHUB_REPO_PRIORITY="webargs=2,konch=3"
export COORDINATES=23.3,50.0
export LOG_LEVEL=DEBUG
Parse them with environs...
```
使用`environs`解析：

```python
from environs import Env


env = Env()
env.read_env()  # read .env file, if it exists
# required variables
gh_user = env("GITHUB_USER")  # => 'sloria'
secret = env("SECRET")  # => raises error if not set

# casting
max_connections = env.int("MAX_CONNECTIONS")  # => 100
ship_date = env.date("SHIP_DATE")  # => datetime.date(1984, 6, 25)
ttl = env.timedelta("TTL")  # => datetime.timedelta(0, 42)
log_level = env.log_level("LOG_LEVEL")  # => logging.DEBUG

# providing a default value
enable_login = env.bool("ENABLE_LOGIN", False)  # => True
enable_feature_x = env.bool("ENABLE_FEATURE_X", False)  # => False

# parsing lists
gh_repos = env.list("GITHUB_REPOS")  # => ['webargs', 'konch', 'ped']
coords = env.list("COORDINATES", subcast=float)  # => [23.3, 50.0]

# parsing dicts
gh_repos_priorities = env.dict(
    "GITHUB_REPO_PRIORITY", subcast_values=int
)  # => {'webargs': 2, 'konch': 3}
```

### 关于区分不同环境

我们可以把所有项目中涉及到的变量写到`.env`配置文件中，然后对于一些针对不同的项目环境（开发、测试、生产）中的变量，使用`config.py`中的不同类进行获取并区分。

## 总结

按照[Hello, Flask!|管理环境变量 - Flask 入门教程](https://read.helloflask.com/c2-hello#guan-li-huan-jing-bian-liang) 章节给出的建议，分别使用`.env` 和 `.flaskenv` 来管理开发模式下的环境变量，这两个文件通常写入的内容如下：

### .env

不能公开的敏感数据，除非是私有项目，否则绝对不能提交到 Git 仓库中。比如：

*   密钥
*   数据库 URL
*   邮件服务器或其他第三方服务的密码 / 密钥 / 令牌值

### .flaskenv

和 Flask 开发服务器相关的几个环境变量，比如：

*   FLASK_ENV
*   FLASK_APP
*   FLASK_DEBUG
*   FLASK_RUN_PORT 等

目前内置配置变量的列表见：[配置管理 — Flask 中文文档（ 1.1.1 ）](https://dormousehole.readthedocs.io/en/latest/config.html#id4)
此外，你可以这样获取默认的环境变量配置：
```bash
>>> from flask import Flask
>>> app = Flask(__name__.split(".")[0])
>>> app.config
```
在项目中加入这块代码，则可以获取项目中使用的环境变量。

而其他一些与你代码中有关的变量配置，则直接写到配置脚本（比如 `config.py` 和 `settings.py`）来实现控制。其中`settings.py`中存放我们程序员编写代码时可能需要修改的变量，而`config.py`用于控制不同的应用环境时使用不同的环境变量。

这部分代码可以在此处找到：

![tag v0.1 ](https://cdn.jsdelivr.net/gh/masantu/statics/images/20210117202012.png)

## 相关链接
- [配置管理 — Flask 中文文档（ 1.1.1 ）](https://dormousehole.readthedocs.io/en/latest/config.html)
- [关于 Flask 通过.env 加载环境变量的两个坑 - Flask - HelloFlask 论坛](https://discuss.helloflask.com/t/topic/128)
- [Start using '.env' for your Flask project and stop using environment variables for development! How and why. | ITNEXT](https://itnext.io/start-using-env-for-your-flask-project-and-stop-using-environment-variables-for-development-247dc12468be)
- [Python,environ 解惑 - bay1 - 博客园](https://www.cnblogs.com/bay1/p/10982310.html)
