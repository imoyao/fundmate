---
title: 数据库的选择及使用（待整理）
---

## 选择✨

1. 使用 MySQL 作为存储数据库；
2. 使用 SQLAlchemy 作为数据库构造的工具；
3. ~~在线工具 [Freedgo](https://www.freedgo.com/new/my/my-design.html) 制作；~~ 使用navicat构造数据库模型
    ::: warning
    注意：如果提示连接失败，请尝试排查以下错误：
    1. 网络是否连接正常；
    2. 防火墙是否开放3306默认端口（或自定义）；
    3. 数据库是否放开远程连接；
    参见：[记一次Navicat for MySQL 10060错误的解决过程 - SegmentFault 思否](https://segmentfault.com/a/1190000022046000)
    :::

## 字段类型

[一篇文章看懂 mysql 中 varchar 能存多少汉字、数字，以及 varchar(100)和 varchar(10)的区别 - 那些年的代码 - 博客园](https://www.cnblogs.com/zhuyeshen/p/11642211.html)

## 数据表

在设计数据库的时候，我们以基金、用户、基金经理作为三个数据主体进行发散。基金和用户之间通过申购、赎回行为联系起来；基金与经理之间通过管理行为联系起来；而基金自身又有每日净值，申购、赎回费率等属性。

1. 我们首先根据设计绘制出 E-R 图
2. 然后根据 E-R 图导出 SQL 文件
3. 然后生成数据表
```
mysql> create database {DB_NAME};      # 创建数据库
mysql> use {DB_NAME};                  # 使用已创建的数据库 
mysql> set names utf8;           # 设置编码
mysql> source {SQL_PATH} # 导入备份数据库
```
其他用到的命令：
```sql
SELECT concat('DROP TABLE IF EXISTS ', table_name, ';')
FROM information_schema.tables
WHERE table_schema = '{DB_NAME}';
```
4. 数据库设计

最后编写 ORM 代码；当然，我们也可以使用[sqlacodegen](https://github.com/agronholm/sqlacodegen)自动生成 ORM。
```
# default
engine = create_engine('mysql://scott:tiger@localhost/foo')

# mysqlclient (a maintained fork of MySQL-Python)
engine = create_engine('mysql+mysqldb://scott:tiger@localhost/foo')

# PyMySQL
engine = create_engine('mysql+pymysql://scott:tiger@localhost/foo')
```
默认情况下，Flask-SQLAlchemy会根据模型类的名称生成一个表名称，生成规则如下：
```
FooBar --> foo_bar  # 驼峰命名改为小写下划线
Baz --> baz         # 单个单词的改为小写
```
> Some parts that are required in SQLAlchemy are optional in Flask-SQLAlchemy. For instance the table name is automatically set for you unless overridden. It’s derived from the class name converted to lowercase and with “CamelCase” converted to “camel_case”. To override the table name, set the `__tablename__` class attribute.

来源见此：[Declaring Models — Flask-SQLAlchemy Documentation (2.x)](https://flask-sqlalchemy.palletsprojects.com/en/2.x/models/#declaring-models)

### 关系对应模型

#### 一对多

所谓的一对多就是外键设计，在 [idealyard](https://github.com/imoyao/idealyard) 项目中，我们的文章和作者就是一对多的关系。本例中，我们的用户（User）和账户（Account）也是这种关系。

- relationship & ForeighKey

大多数情况下, db.relationship() 都能自行找到关系中的外键, 但有时却无法决定把 哪一列作为外键。 

例如, 如果 User 模型中有两个或以上的列定义为 Role 模型的外键, SQLAlchemy 就不知道该使用哪列。如果无法决定外键,你就要为 db.relationship() 提供额外参数,从而确定所用外键。

#### 定义关系属性

关系属性在关系的出发侧定义，即一对多关系的“一”这一侧。一个作者拥有多篇文章，在 [User模型]((https://github.com/imoyao/idealyard/blob/master/back/models.py) 中，我们定义了一个articles属性来表示对应的多篇文章：
```
articles = db.relationship('Article')
```

在本项目中，我们以基金净值（`DailyWorth`）为例说明用法：

每个基金每天都会有一个净值，所以在净值表中，每个基金会有多个对应值。则我们很容易写出这样的代码：
```python
# 在Fund侧
worths = db.relationship('DailyWorth')
```

通过`backend/fundmate/database.relationship`定义。用法参见`backend.fundmate.database.reference_col`。

此处我们参考 [demo-cookiecutter-flask/models.Role](https://github.com/jamescurtin/demo-cookiecutter-flask/blob/master/my_flask_app/user/models.py) 写为：
```python
# 在DailyWorth侧
fund_id = reference_col('funds', column_kwargs={'comment': '基金编号'})
fund = relationship('Fund', backref='daily_worth')
```
::: info
> The [relationship.back_populates](http://docs.sqlalchemy.org/en/rel_1_0/orm/relationship_api.html target=) parameter is a newer version of a very common SQLAlchemy feature called [relationship.backref](http://docs.sqlalchemy.org/en/rel_1_0/orm/relationship_api.html target=). The [relationship.backref](http://docs.sqlalchemy.org/en/rel_1_0/orm/relationship_api.html target=) parameter hasn’t gone anywhere and will always remain available! The [relationship.back_populates](http://docs.sqlalchemy.org/en/rel_1_0/orm/relationship_api.html target=) is the same thing, except a little more verbose and easier to manipulate. For an overview of the entire topic, see the section [Linking Relationships with Backref](http://docs.sqlalchemy.org/en/rel_1_0/orm/backref.html target=).

参见：[Object Relational Tutorial — SQLAlchemy 1.3 Documentation](https://docs.sqlalchemy.org/en/13/orm/tutorial.html#building-a-relationship)
:::

- relationship vs backref
[python - When do I need to use sqlalchemy back_populates? - Stack Overflow](https://stackoverflow.com/questions/39869793/when-do-i-need-to-use-sqlalchemy-back-populates)

> backref is more succinct because you don't need to declare the relation on both classes, but in practice I find it not worth to save this on line. I think back_populates is better, not only because in python culture "Explicit is better than implicit" (Zen of Python), but when you have many models, with a quick glance at its declaration you can see all relationships and their names instead of going over all related models. Also, a nice side benefit of back_populates is that you get auto-complete on both directions on most IDEs.

backref更为简洁，因为您不需要在两个类上都声明该关系，但是实践中，我发现这一点不值得作为准则。
基于以下两点，我认为back_populates更好：
1. 不仅因为在python文化中，“显式比隐式更好”（Python之禅）；
2. 而且当我们创建了许多模型时，快速浏览一下它的声明，就可以看到所有关系及其名称，而不用去在所有相关模型上慢慢查找；
3. 另外，back_populates的一个不错的好处是，您可以在大多数IDE的两个方向上自动完成。（TODO：此处不知道如何实现）

通过db.relationship()，Role 模型有了一个可以获得对应角色所有用户的属性users。默认是列表形式，lazy='dynamic'时返回的是一个 query 对象。即relationship提供了 Role 对 User 的访问。

而backref正好相反，提供了 User 对 Role 的访问。

不妨设一个 Role 实例为 user_role，一个 User 实例为 u。relationship 使 user_role.users 可以访问所有符合角色的用户，而 backref 使 u.role 可以获得用户对应的角色。

- [Flask-SQLAlchemy 中的 relationship & backref_一个菜鸟的博客-CSDN博客](https://blog.csdn.net/mr_hui_/article/details/83217566)
- [讲解一下SQLAlchemy中的backref？ - 知乎](https://www.zhihu.com/question/38456789)
- [python - When do I need to use sqlalchemy back_populates? - Stack Overflow](https://stackoverflow.com/questions/39869793/when-do-i-need-to-use-sqlalchemy-back-populates)

#### 多对多关系

:::
如果你想要用多对多关系，你需要定义一个用于关系的辅助表。对于这个辅助表， 强烈建议**不要**使用模型，而是采用一个实际的表。
:::

如果关联对象之间只需要用id关联起来，如：
```
association_table = Table('association', Base.metadata,
    Column('left_id', Integer, ForeignKey('left.id')),
    Column('right_id', Integer, ForeignKey('right.id'))
)
```

[Basic Relationship Patterns — SQLAlchemy 1.4 Documentation](https://docs.sqlalchemy.org/en/14/orm/basic_relationships.html#association-object)

[Flask/SQLAlchemy - Difference between association model and association table for many-to-many relationship? - Stack Overflow](https://stackoverflow.com/questions/30406808/flask-sqlalchemy-difference-between-association-model-and-association-table-fo)

::: warning
> 实践中的SQLAlchemy的"relationship"在一定程度上反而导致了整体表关联关系的极大复杂化，还有效率的极其低下。
> 如果你的数据库只有两个表的话，那么relationship随便定义随便用。如果只有几百条数据的话，那么也请随便玩。

但是，当数据库中有数十个表以上，单个关联层级就多过三个表以上层层关联，而且各个数据量以万为单位。那么，"relationship"会把整个人都搞垮，简直还不如手写SQL语句清晰好理解，并且效率也差在了秒级与毫秒级的区别上。

SQLAlchemy只能很轻松handle Many to Many，但是如果是常见的Many to Many to Many，或者是Many to Many to Many to Many，那简直就是噩梦。

用SQLAlchemy建立各种ORM类对象，不要用内置的关联，直接在查询的时候手动SQL语句！
:::

经过实践，我的建议是：
::: tip

- 容易SQL-Injection注入的地方，用SQLAlchemy的query
- 创建ORM对象时候，用SQLAlchemy
- 多层关联的时候，不要用SQLAlchemy
- 查询的时候，用SQL
- 插入数据的时候，不要用SQLAlchemy。（官方都说明了插入百万级的时候，和SQL插件是秒级的）
:::

[深究SQLAlchemy中的表关系 Table Relationships - SegmentFault 思否](https://segmentfault.com/a/1190000018006031)
此处争议讨论参阅：[项目里该不该用ORM？ - 知乎](https://www.zhihu.com/question/28537109)

#### 多态关联（Polymorphic Associations）

在记录费率问题时，我们需要对申购和赎回分别记录

原文：[polymorphic associations - Possible to do a MySQL foreign key to one of two possible tables? - Stack Overflow](https://stackoverflow.com/questions/441001/possible-to-do-a-mysql-foreign-key-to-one-of-two-possible-tables) 中文版：[MySQL 表中的同一个字段能否同时是两个表的外键 - 简书](https://www.jianshu.com/p/915dc58d2d0f)

[python - Flask-SQLAlchemy polymorphic association - Stack Overflow](https://stackoverflow.com/questions/57000045/flask-sqlalchemy-polymorphic-association)

#### 参考阅读

- [SQLAlchemy 学习笔记（三）：ORM 中的关系构建 - 於清樂 - 博客园](https://www.cnblogs.com/kirito-c/p/10900024.html)
- [SQLAlchemy ORM教程之三：Relationship - 简书](https://www.jianshu.com/p/9771b0a3e589)
- [SQLAlchemy进阶 | 飞污熊博客](https://www.xncoding.com/2016/03/07/python/sqlalchemy02.html)

5. 数据库创建

初始化时，我们需要定义初始化函数，参见：`fundmate.commands.init_db`，之后将数据库配置写入环境变量；我们可以直接以`DATABASE_URL`的方式给出数据库的链接，也可以使用更细粒度的控制方式，以实现每一种环境使用不同的配置方式。一种可参考的配置方式如下：
```
DATABASE_URL=sqlite:////tmp/dev.db
MYSQL_USER=
MYSQL_PASSWORD=
MYSQL_DB=
```
需要注意的是：
> 当继承db.Model基类的子类被声明创建时，根据db.Model基类继承的元类中设置的行为，类声明后会将表信息注册到db.Model.metadata.tables属性中。
>
>`create_all()`方法被调用时正是通过这个属性来获取表信息。因此，当我们调用create_all()前，需要确保模型类被声明创建。如果模型类存储在单独的模块中，不导入该模块就不会执行其中的代码，模型类便不会被创建，进而便无法注册表信息到db.Model.metadata.tables中，所以这时需要导入相应的模块。

参见：
1. [sqlalchemy中用db.create_all()无法建表？ - 知乎](https://www.zhihu.com/question/21489726)
2. [使用Flask-SQLAlchemy调用create_all()前是否需要导入模型类？为什么？ - 知乎](https://www.zhihu.com/question/284904297)

`fundmate.app.register_shell_context`函数中需要注册之后调用`flask init-db`才能生成需要的数据表。

数据库在初始化构建完成之后，我们就可以进行开发了。但是在实际的开发过程中，我们的设计会跟着开发不断迭代进化。这个时候我们就需要进行数据库的迁移。

6. 数据库更新和降级

数据库迁移的主要目的是保留我们之前数据的记录，同时一旦发现数据库设计出现问题，可以通过降级回滚到之前的较旧版本中去。

此处我们使用 [Flask-Migrate](https://flask-migrate.readthedocs.io/en/latest/) 扩展实现。具体使用英文不好的同学可以参考此处：[Flask-migrate基本使用方法 - sablier - 博客园](https://www.cnblogs.com/sablier/p/11084080.html)。

关于`SQLALCHEMY_COMMIT_ON_TEARDOWN`的讨论：
- [关于Flask-SQLAlchemy事务提交有趣的探讨 - SegmentFault 思否](https://segmentfault.com/a/1190000007818952)
- [SQLAlchemy 两种不同方式 commit() 时间开支的问题 - 知乎](https://zhuanlan.zhihu.com/p/27974385)
- [关于flask-sqlalchemy中数据库操作的问题整理 - 简书](https://www.jianshu.com/p/ead613514f18)

### E-R 图

使用[freedgo](https://www.freedgo.com)生成 ER 图之后 [格式化](https://tool.oschina.net/codeformat/sql) ，当然我们也可以选择导入 [dbdiagram.io](https://dbdiagram.io/) 生成图片。
改成 [Navicat GUI | DB Admin Tool for MySQL, PostgreSQL, MongoDB, MariaDB, SQL Server, Oracle & SQLite client](https://www.navicat.com/en/) 画图

[用Navicat制作ER图及与SQL互相转化 | 王柏元的博客 | 博学广问，自律静思](https://wangbaiyuan.cn/sql-and-use-navicat-to-make-er-diagram-and-interactive.html)

::: warning
```sql
# 修改允许远程连接
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%'IDENTIFIED BY '{PASS_WORD}' WITH GRANT OPTION;
```
:::


![](https://cdn.jsdelivr.net/gh/masantu/statics/images/fundmate-ER.png)

::: warning
该图示只用于数据库关系设计，具体字段定义以代码中实现为准！
:::

在线预览参见[基伴 - freedgo.com](https://www.freedgo.com/draw-index.html#O100929310168186882)

### SQL 语句

SQL 文件详见 [此处](https://github.com/imoyao/fundmate/blob/master/db/fmt.sql) 。

### 疑难问题

- 阶梯费率
::: tip
类似于文章标签表，我们可以把收费费率看作一个标签，每一个文章（基金 ID）对应多个标签（阶梯费率），以日期的起始天数作为每一行记录去标识收费标准。

参阅：[数据库关于阶梯表的设计-CSDN 论坛](https://bbs.csdn.net/topics/390747950)
:::

- Relationships

[Relationships Between SQLAlchemy Data Models](https://hackersandslackers.com/sqlalchemy-data-models/)

- 多账本

需要一个账本表和一个用户账本关系表

参阅：[我的账本_liuhong1.happy_新浪博客](http://blog.sina.com.cn/s/blog_825442790102uzdk.html)

## 注意事项

1. 连接池
2. 超时释放问题

### 规范

- [数据库设计中的命名规范 - 简书](https://www.jianshu.com/p/7e60dbd59138)
- [建议收藏 - 专业的 MySQL 开发规范](https://juejin.cn/post/6844903953608802312)
- [数据库设计中的命名规范 - 雪域迷城 - OSCHINA - 中文开源技术交流社区](https://my.oschina.net/NorthOcean/blog/227328)

### 设计

- [数据库设计 Step by Step 篇目整理及下载地址 - 知行思新 - 博客园](https://www.cnblogs.com/DBFocus/archive/2011/10/12/2208580.html)