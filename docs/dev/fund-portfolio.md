---
title: 基金组合功能设计与实现
---

## 组合和账本的联系

实盘投资型：创建实盘组合，支持自由买入/卖出、持仓份额转入/转出

资产配置型：选择基金和配比创建组合，按比例买入，系统实时监控持仓偏离度

|      | 资产配置型（回测）                         | 投资记录型（实盘）                                  |
|------|--------------------------------|------------------------------------------|
| 创建流程 | 先选择目标基金设置配比，然后再创建              | 直接创建，无需选择基金和设置配比  |
| 买入   | 输入组合购买金额，系统计算目标基金买入金额，一键购买组合| 自由选择买入基金及金额      |
| 卖出   | 选择组合卖出比例，系统计算目标基金卖出份额，一键卖出组合   | 自由选择卖出基金及份额                              |
| 组合详情 | 按照目标基金及配比生成业绩走势                | 根据实际持仓生成业绩走势，反映组合实盘表现                    |
| 特色功能 | 1.持仓偏离度提醒 <br>  2.发表观点、一键调持仓           | 组合买卖自由度高    |
| 使用场景 | 谋定而后动。<br> 1. 基于资产配置的理念，设置目标基金和投资比例；<br> 2. 先创建组合查看回测结果，观察业绩表现之后再投入  |知行合一。<br> 1.希望组合操作足够灵活，自由度高 <br> 2.建立账户实盘组合，业绩走势可反映实盘表现 |


我们每一个账本可以看成一个实盘型组合，而回测可以作为投资前的投资计划指定。并且可以在实盘创建之后跟踪回测，提供跟踪误差等信息。

## 实现
1. 分析现有基金组合平台，设计数据库model；
2. 实现实盘型组合构建（create）、调仓（update）、更新描述（patch）、删除（delete）操作；
3. 实现组合回测、分析功能；

## 相关链接

- [ ] [MrDujing/FundCombination: 基金组合研究: 利用python，抓取天天基金网、晨星网数据，分析组合持仓、行业分布、基金参数特征，辅助基金组合投资策略制定](https://github.com/MrDujing/FundCombination)

### 组合爬取

- [ ] [Concyclics/db\_big\_homework: 投资组合评比器，基于python3.8和mysql8.0。由Concyclics和wingholy完成主要编程工作，可实现对于蛋卷基金和且慢基金平台投资组合信息的收集和对比。](https://github.com/Concyclics/db_big_homework)

### 组合净值计算

- [ ] [zhixwang/Stock\_calculation: 模拟基金净值的方式，计算A股、港股、美股全市场的个人实仓组合净值变化。](https://github.com/zhixwang/Stock_calculation)

### 分析计算

- [ ] [基于python进行信息爬取，进行基金组合透视分析\_静笃小塾-CSDN博客](https://blog.csdn.net/cheetahzhang/article/details/110527547)
- [ ] [SunshowerC/fund-strategy: 基金投资策略分析，基金回测工具](https://github.com/SunshowerC/fund-strategy)

### 设计实现

- [ ] [如何设计理财中的基金组合产品？ | 人人都是产品经理](http://www.woshipm.com/pd/697327.html)
- [ ] [RichardJerry/Fund: 基金定投、基金组合等相关函数及实例](https://github.com/RichardJerry/Fund)
- [ ] [基金组合管理系统的设计与实现-手机知网](https://wap.cnki.net/touch/web/Dissertation/Article/10004-1017096882.nh.html)

[来源](https://github.com/imoyao/fundmate/issues/230#issuecomment-986163035)