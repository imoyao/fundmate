---
title: 数据库的选择及使用
---

## 选择

1. 使用 MySQL 作为存储数据库；
2. 使用 SQLAlchemy 作为数据库构造的工具；
3. 在线工具 [Freedgo](https://www.freedgo.com/new/my/my-design.html) 制作；

## 字段类型

[一篇文章看懂 mysql 中 varchar 能存多少汉字、数字，以及 varchar(100)和 varchar(10)的区别 - 那些年的代码 - 博客园](https://www.cnblogs.com/zhuyeshen/p/11642211.html)

## 数据表

在设计数据库的时候，我们以基金、用户、基金经理作为三个数据主体进行发散。基金和用户之间通过申购、赎回行为联系起来；基金与经理之间通过管理行为联系起来；而基金自身又有每日净值，申购、赎回费率等属性。

1. 我们首先根据设计绘制出 E-R 图
2. 然后根据 E-R 图导出 SQL 文件
3. 然后生成数据表
```
mysql> create database {DB_NAME};      # 创建数据库
mysql> use abc;                  # 使用已创建的数据库 
mysql> set names utf8;           # 设置编码
mysql> source /home/abc/abc.sql  # 导入备份数据库
```
4. 最后编写 ORM 代码；当然，我们也可以使用[sqlacodegen](https://github.com/agronholm/sqlacodegen)自动生成 ORM。
```
# default
engine = create_engine('mysql://scott:tiger@localhost/foo')

# mysqlclient (a maintained fork of MySQL-Python)
engine = create_engine('mysql+mysqldb://scott:tiger@localhost/foo')

# PyMySQL
engine = create_engine('mysql+pymysql://scott:tiger@localhost/foo')
```

### E-R 图

使用[freedgo](https://www.freedgo.com)生成 ER 图之后 [格式化](https://tool.oschina.net/codeformat/sql) ，当然我们也可以选择导入 [dbdiagram.io](https://dbdiagram.io/) 生成图片。

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