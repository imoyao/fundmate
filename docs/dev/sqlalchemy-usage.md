---
title: SqlAlchemy 使用案例记录
---

## 基金费率表

基金有申购规则和赎回规则之分，其中申购规则是按照购入金额进行计算的，而赎回规则是按照买入天数划分标准进行计算的。
所以我们创建三个表模型，`InRule`记录申购和买入的起始金额，`OutRule`记录赎回的规则划分。在`FundRate`中记录具体的费率标准。

则此时，一个 rate_id 可能对应买入或者卖出两张表的 id。
完整的对应关系变为：

```plain
Fund > FundRate O2M
FundRate > **Rule  O2M
```

这种对应关系我们可以使用`sqlalchemy.ext.hybrid`包中的`@hybrid_property`装饰器来定义这种关系。参见[此处](https://stackoverflow.com/a/60053408/14295718)

## ChoiceType

使用自定义的`ChoiceType`，我们除了参照 [python - SQLAlchemy - How to make "django choices" using SQLAlchemy? - Stack Overflow](https://stackoverflow.com/questions/6262943/sqlalchemy-how-to-make-django-choices-using-sqlalchemy) 实现自定义的类型之外，还需要注意的是使用`flask_migrate`生成迁移的时候，如果不修改`backend/migrations/`下的`env.py`和`script.py.mako`，那么定义是无法使用的。具体参阅：[Issue #259 · imoyao/fundmate](https://github.com/imoyao/fundmate/issues/259)
