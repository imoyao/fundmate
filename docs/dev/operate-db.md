---
title: 对你的代码进行类型提示
permalink: /dev/type-hints
---
## 关于`synchronize_session`参数

在创建/删除组合时我们编写了如下的：[代码](https://github.com/imoyao/fundmate/blob/90a8b882b42c99ab605c1ef95c943f536a8bc29a/backend/fundmate/fund/views.py#L275)
```python
fpo_adjust_history.delete(synchronize_session=False)
```
其中的`synchronize_session`参数可能让我们困惑，一起学习一下。
[Session Basics — SQLAlchemy 1.4 Documentation](https://docs.sqlalchemy.org/en/14/orm/session_basics.html#selecting-a-synchronization-strategy)

> With both the 1.x and 2.0 form of ORM-enabled updates and deletes, the following values for synchronize_session are supported:
> 
> `False` - don’t synchronize the session. This option is the most efficient and is reliable once the session is expired, which typically occurs after a commit(), or explicitly using expire_all(). Before the expiration, objects that were updated or deleted in the database may still remain in the session with stale values, which can lead to confusing results.
>
> `fetch` - Retrieves the primary key identity of affected rows by either performing a SELECT before the UPDATE or DELETE, or by using RETURNING if the database supports it, so that in-memory objects which are affected by the operation can be refreshed with new values (updates) or expunged from the Session (deletes). Note that this synchronization strategy is not available if the given update() or delete() construct specifies columns for UpdateBase.returning() explicitly.
>
> `evaluate` - Evaluate the WHERE criteria given in the UPDATE or DELETE statement in Python, to locate matching objects within the Session. This approach does not add any round trips and in the absence of RETURNING support is more efficient. For UPDATE or DELETE statements with complex criteria, the 'evaluate' strategy may not be able to evaluate the expression in Python and will raise an error. If this occurs, use the 'fetch' strategy for the operation instead.

为了便于理解，我们做一个简单的实验：
使用`flask shell` 打开 flask 命令行：

```python
In [1]: fpo_adjust_history = FundPortfolioAdjustHistory.query.filter_by(portfolio_code='010953')

In [2]: fpo_adjust_history
Out[2]: <flask_sqlalchemy.BaseQuery at 0x7faf9253a190>

In [3]: fpo_adjust_history.delete(synchronize_session=False)
Out[3]: 1

```
此时查询数据库
```sql
SELECT
    count(*)
FROM
    fund_portfolio
WHERE
    portfolio_code = '010953';
```
我们可以发现数据没有删除；只有当我们使用`db.session.commit()`指令显式告诉数据库删除时，数据才会被真正删除；而如果后续操作出错，可以使用`db.session.rollback()` 回滚操作；