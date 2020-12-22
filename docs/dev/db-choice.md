---
title: 数据库的选择及使用
---

## 选择

1. 使用MySQL作为存储数据库；
2. 使用 SQLAlchemy 作为数据库构造的工具；
3. 在线工具 [Freedgo](https://www.freedgo.com/new/my/my-design.html) 制作；

## 字段类型

[一篇文章看懂mysql中varchar能存多少汉字、数字，以及varchar(100)和varchar(10)的区别 - 那些年的代码 - 博客园](https://www.cnblogs.com/zhuyeshen/p/11642211.html)

## 数据表

### SQL语句

```sql
CREATE TABLE IF NOT EXISTS User (	id INT PRIMARY KEY comment '自增id',
	userid INT(10) UNSIGNED comment '用户编号',
	name VARCHAR(16) comment '用户名',
	password VARCHAR(40) NOT NULL comment '用户密码',
	email VARCHAR(16) comment '注册邮箱',
	phone_num VARCHAR(11) comment '注册手机号',
	create_time TIMESTAMP comment '注册时间'
);
alter table User add constraint User_userid_fk0  foreign key (userid) references HandPicked (uid);
alter table User add constraint User_userid_fk1  foreign key (userid) references Redeme (uid);
alter table User add constraint User_name_fk0  foreign key (name) references Purchase (uid);
comment on table User is '用户表';
CREATE TABLE IF NOT EXISTS HandPicked (	id int PRIMARY KEY,
	fid VARCHAR(20) comment '基金编号',
	uid VARCHAR(20) comment '用户编号',
	pick_time TIMESTAMP comment '收藏时间',
	comment VARCHAR(30) comment '备注'
);
comment on table HandPicked is '自选基金';
CREATE TABLE IF NOT EXISTS Fund (	id int PRIMARY KEY,
	name VARCHAR(30) comment '基金名称',
	fid VARCHAR(16) comment '基金编号',
	type TINYINT UNSIGNED comment '基金类型'
);
alter table Fund add constraint Fund_id_fk0  foreign key (id) references Redeme (fid);
alter table Fund add constraint Fund_fid_fk0  foreign key (fid) references Purchase (fid);
alter table Fund add constraint Fund_fid_fk1  foreign key (fid) references HandPicked (fid);
alter table Fund add constraint Fund_fid_fk2  foreign key (fid) references DailyWorth (fid);
comment on table Fund is '基金表';
CREATE TABLE IF NOT EXISTS Purchase (	id int PRIMARY KEY,
	fid VARCHAR(10) comment '所购买的基金',
	uid VARCHAR(10) comment '购买用户',
	amount INT(10) comment '购买金额',
	date DATE default  current_date comment '购买日期（确认日期）',
	comment VARCHAR(30) comment '复盘备注'
);
comment on table Purchase is '申购记录表';
CREATE TABLE IF NOT EXISTS Redeme (	id int PRIMARY KEY,
	fid VARCHAR(10) comment '所购买的基金',
	uid VARCHAR(10) comment '购买用户',
	amount INT(10) comment '购买金额',
	date DATE comment '赎回日期',
	comment VARCHAR(30) comment '复盘备注'
);
comment on table Redeme is '赎回记录表';
CREATE TABLE IF NOT EXISTS DailyWorth (	id int PRIMARY KEY,
	fid VARCHAR(10) comment '基金编号',
	pirce FLOAT(4) comment '基金单价'
);
comment on table DailyWorth is '每日净值表';
```
### E-R图

[fundmate-.xml - freedgo.com](https://www.freedgo.com/erd-index.html#O100835824836280322)

### 阶梯费率

看来看去，第一张表中，增加一个计费阶梯ID，关联到你的第二张阶梯计费定义表的fid，这个字段的值，则是在你生成数据的时候，在程序逻辑去处理，亦或者是，使用触发器，在插入计费表的时候，自动填充所属阶梯id，这样，就关联起来了。同时，这样设计的好处在于，每一个人的计费阶梯，都会有对应的阶梯定义。这是符合数据库设计的。
[(2条消息) 数据库关于阶梯表的设计-CSDN论坛](https://bbs.csdn.net/topics/390747950)

## 注意事项

1. 连接池
2. 超时释放问题

## 相关链接

[有什么画ER关系比较好用的软件图？ - 知乎](https://www.zhihu.com/question/20290434)

### 规范
- [数据库设计中的命名规范 - 简书](https://www.jianshu.com/p/7e60dbd59138)
- [建议收藏 - 专业的MySQL开发规范](https://juejin.cn/post/6844903953608802312)
- [数据库设计中的命名规范 - 雪域迷城 - OSCHINA - 中文开源技术交流社区](https://my.oschina.net/NorthOcean/blog/227328)

### 设计

- [数据库设计Step by Step篇目整理及下载地址 - 知行思新 - 博客园](https://www.cnblogs.com/DBFocus/archive/2011/10/12/2208580.html)