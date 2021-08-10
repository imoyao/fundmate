---
title: SqlAlchemy 使用案例记录
---

## 基金费率表

基金有申购规则和赎回规则之分，其中申购规则是按照购入金额进行计算的，而赎回规则是按照买入天数划分标准进行计算的。
所以我们创建三个表模型，`InRule`记录申购和买入的起始金额，`OutRule`记录赎回的规则划分。在`FundRate`中记录具体的费率标准。

则此时，一个rate_id可能对应买入或者卖出两张表的id。
完整的对应关系变为：
```plain
Fund > FundRate O2M
FundRate > **Rule  O2M
```
这种对应关系我们可以使用`sqlalchemy.ext.hybrid`包中的`@hybrid_property`装饰器来定义这种关系。参见[此处](https://stackoverflow.com/a/60053408/14295718)