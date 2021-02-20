---
title: 数据库的选择及使用
---

## 选择

1. 使用 MySQL 作为存储数据库；
2. 使用 SQLAlchemy 作为数据库构造的工具；
3. ~~在线工具 [Freedgo](https://www.freedgo.com/new/my/my-design.html) 制作；~~ 使用navicat构造数据库模型

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

所谓的一对多就是外键设计，在idealyard项目中，我们的文章和作者就是一对多的关系。本例中，我们的用户（User）和账户（Account）就是这种关系。

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