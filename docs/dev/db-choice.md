---
title: 数据库的选择及使用
---

## 选择

1. 使用MySQL作为存储数据库；
2. 使用 SQLAlchemy 作为数据库构造的工具

## 数据表
```sql
create table data_day(
              id int primary key auto_increment,
              date varchar(11) not null,
              code varchar(11) not null,
              open float(7,2) not null,
              close float(7,2) not null,
              hign float(7,2) not null,
              low float(7,2) not null
              )engine=innodb, charset=utf8

create index code_index on data_day(code)
```
1. 代码表
如 股票代码:10000 股票名称：浦发银行 上市日期 
2. 历史净值表
代码 开盘价格 收盘价格 最高价格 最低价格 日期
3. 基金公司表
如10000, 公司 ，F10信息

## 注意事项

1. 连接池
2. 超时释放问题

## 相关链接

[有什么画ER关系比较好用的软件图？ - 知乎](https://www.zhihu.com/question/20290434)