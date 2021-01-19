---
title: 凡有操作，必留日志 | 用户操作日志模块开发
---
## 前言

系统开发中我们经常使用一些日志框架（如JAVA中的 log4j/logback/slf4j 等），用来调试、追踪、输出系统运行状况等，这些日志通常是给程序员看的，暂且叫它”系统日志“；而对于普通用户来说，也需要一个日志功能，可以方便查阅自己做过哪些操作，这些日志是面向普通用用户的，暂且叫它 ”用户操作日志“。

## 凡有操作，必留日志

![踏雪寻梅](http://img-arch.pconline.com.cn/images/upload/upc/tx/photoblog/1502/04/c10/2739791_1423038522443.jpg)

::: tip
该文标题化用埃德蒙•罗卡定律：“凡有接触，必留痕迹”（Every contact leaves a trace）。
参阅：[罗卡定律：凡有接触，必留痕迹| 果壳 科技有意思](https://www.guokr.com/article/436744/)
:::

## 系统日志

```python
from loguru import logger


debugfile = '/var/log/rfr.log'
# logger.remove(handler_id=None)  # 不输出stdout
logger.add(debugfile,
           format="{time:YYYY-MM-DD at HH:mm:ss} {level} at Line: {line} Model_name is: **{name}**, Function:{function}, MSG is:{message}",
           rotation="50 MB",
           encoding='utf-8',
           enqueue=True, retention="10 days")
```
参阅：[Python 中更优雅的日志记录方案 loguru | 静觅](https://cuiqingcai.com/7776.html)


## 相关链接

- [用户操作日志模块如何开发? - 知乎](https://www.zhihu.com/question/26848331)
- [平台用户操作日志模块设计 - 简书](https://www.jianshu.com/p/872bb374596d)
- [浅谈管理系统操作日志设计（附操作日志类） - 胡尐睿丶 - 博客园](https://www.cnblogs.com/hooray/archive/2012/09/05/2672133.html)
- [平台用户操作日志模块设计 - 简书](https://www.jianshu.com/p/872bb374596d)
- [当我们在使用 Flask 时，如何记录日志_于振-CSDN 博客_flask 打印日志](https://blog.csdn.net/iszhenyu/article/details/56846551)
- [如何优雅的在flask中记录log - SegmentFault 思否](https://segmentfault.com/a/1190000018087099)
- [django 如何实现数据的用户操作记录? - V2EX](https://v2ex.com/t/603768)