---
title: 凡有操作，必留日志 | 用户操作日志模块开发
tag:
    - 软件工程plainplainplainplainplainplainplainplainplain
---

## 凡有操作，必留日志

![踏雪寻梅](http://img-arch.pconline.com.cn/images/upload/upc/tx/photoblog/1502/04/c10/2739791_1423038522443.jpg)

::: tip
该文标题化用埃德蒙•罗卡定律：“凡有接触，必留痕迹”（Every contact leaves a trace）。
参阅：[罗卡定律：凡有接触，必留痕迹| 果壳 科技有意思](https://www.guokr.com/article/436744/)
:::

## 前言

系统开发中我们经常使用一些日志框架（如 JAVA 中的 log4j/logback/slf4j 等），用来调试、追踪、输出系统运行状况等，这些日志通常是给程序员看的，暂且叫它“系统日志”；而对于普通用户来说，也需要一个日志功能，可以方便查阅自己做过哪些操作，这些日志是面向普通用用户的，暂且叫它 “用户操作日志”。

## 系统日志
系统日志方面，我们抛弃掉 Python 中自带的 logging 模块，而是使用开源社区中的`loguru`模块。
```python
from loguru import logger


debugfile = '/var/log/fmp.log'
# logger.remove(handler_id=None)  # 不输出stdout
logger.add(debugfile,
           format="{time:YYYY-MM-DD at HH:mm:ss} {level} at Line: {line} Model_name is: **{name}**, Function:{function}, MSG is:{message}",
           rotation="50 MB",
           encoding='utf-8',
           enqueue=True, retention="10 days")
```
详情参阅本人转载的这篇文章：[Python 中更优雅的日志记录方案 loguru | 别院牧志知识库](https://wiki.masantu.com/pylibs/loguru/)

## 用户日志
用户操作日志应该记录业务层面的日志，或者说是用例层面，可能涉及操作数据库的多张表，甚至不仅操作数据库，所以简单记录表的增删改查是不够完善的。
用户操作日志模块应该比较常见，但凡重复开发率较高的模块，都会有人去把它抽离，做成一个比较独立的模块或类库，比如登录注册/权限管理/认证授权等，注册方式多种，权限管理更是复杂，各具体项目差异太大，但还是有 shiro，spring security 这种安全框架，将不可变抽象成稳定的接口，将可变开放。
## 模型设计
 单一切面能否实现用户操作日志的记录。
### 上层切面
在业务入口处：

- 优点
1. 贴近业务逻辑
因为 startTask 表明了我们要进行的业务逻辑的操作类型，而后面的操作参数则表明了业务逻辑的参数。
- 缺点
无法反映真实数据变动
1. 记录不一定准确，可能在处理途中发生了变化
2. 可能失败，记录无效日志
### 下层切面
- 优点
信息是准确的
- 缺点
无法获得编辑前的旧对象
脱离业务逻辑
一个最终数据库的操作可能是多个调用引起的，http 的 patch 操作，可能只更新了一个单独值，没有必要全部记录
### 混合切面
以下层信息为主（因为它准确），以上层信息为辅（因为它包含业务信息），即吸收下层切面的准确性、整合上层切面的业务逻辑信息，并顺便解决旧对象的获取问题。
```python
def update_fund(old_finfo,new_finfo):pass        
```
## 相关链接

- [用户操作日志模块如何开发? - 知乎](https://www.zhihu.com/question/26848331)
- [平台用户操作日志模块设计 - 简书](https://www.jianshu.com/p/872bb374596d)
- [How to Collect, Customize, and Centralize Python Logs | Datadog](https://www.datadoghq.com/blog/python-logging-best-practices/#unify-all-your-python-logs)
- [浅谈管理系统操作日志设计（附操作日志类） - 胡尐睿丶 - 博客园](https://www.cnblogs.com/hooray/archive/2012/09/05/2672133.html)
- [平台用户操作日志模块设计 - 简书](https://www.jianshu.com/p/872bb374596d)
- [当我们在使用 Flask 时，如何记录日志_于振-CSDN 博客_flask 打印日志](https://blog.csdn.net/iszhenyu/article/details/56846551)
- [如何优雅的在 flask 中记录 log - SegmentFault 思否](https://segmentfault.com/a/1190000018087099)
- [django 如何实现数据的用户操作记录? - V2EX](https://v2ex.com/t/603768)