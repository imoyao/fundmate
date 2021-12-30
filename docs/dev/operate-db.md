---
title: SQLAlchemy 使用过程中的一些特殊使用记录
permalink: /dev/db-operations
---
## 关于`synchronize_session`参数

在创建/删除组合时我们编写了如下的：[代码](https://github.com/imoyao/fundmate/blob/90a8b882b42c99ab605c1ef95c943f536a8bc29a/backend/fundmate/fund/views.py#L275)
```python
fpo_adjust_history.delete(synchronize_session=False)
```
其中的`synchronize_session`参数可能让我们感到困惑，一起学习一下。
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

## Nested 与无外键属性处理

在处理基金组合时，我们没有将组合管理者表`FundPortfolioMgr`和组合表`FundPortfolio`关联起来；这样带来一个问题：在获取组合详情信息时，组合管理者信息的获取不够那么直观，那么有什么办法可以将两者关联起来，以使我们的`@output`装饰器可以很好的序列化呢？

1. 分步查询，在 view 函数中将组合管理员信息更新到组合对象中：
```python
fpo = FundPortfolio.query.filter_by(portfolio_code=portfolio_code).one_or_none()
if fpo is not None:
    mgr_code = fpo.mgr_code
    mgr_inst = FundPortfolioMgr.query.filter_by(code=mgr_code).one_or_none()
    fpo_info = dict()
    fpo_info['manager'] = mgr_inst
    # FIXME: 对于需要联表查询的对象，是否有更加优雅的处理办法（如果不想将字段联表查询），目前的FundPortfolioDetailOutSchema不兼容点查询和get查询
    fpo_info.update(fpo.__dict__)
    return fpo_info
```
这样带来的问题是，我们的`FundPortfolioDetailOutSchema`通用性降低，因为其中个别字段使用`Function`，如此一来，其中的点查询`fpo.manager`将无法获取对象的属性，必须将 object 当作字典处理来获取信息，即`manager.get('name')`，这显然不是一种优雅的处理方式；

2. 使用`@proprety` 将获取管理员信息的方法变为属性
```python
class FundPortfolio(PkModel, CreateDateModel, UpsertMixin):
    ...

    @property
    def manager(self):
        return FundPortfolioMgr.query.filter_by(self.platform !="own",code=self.mgr_code).one_or_none()
```
这样就可以使用点查询了：
```python
fpo = FundPortfolio.query.filter_by(portfolio_code='010949').one_or_none()
print(fpo.managers)
```
这似乎也不是最佳实践。

相关讨论参阅：[python - Is it possible to use a schema for a marshmallow custom field? - Stack Overflow](https://stackoverflow.com/questions/49802142/is-it-possible-to-use-a-schema-for-a-marshmallow-custom-field)

3. 在`FundPortfolio`类中使用内建方法`relationship`
```python
class FundPortfolio(PkModel, CreateDateModel, UpsertMixin):
    ...
    manager = relationship('FundPortfolioMgr',
                       foreign_keys=[mgr_code],
                       primaryjoin='FundPortfolioMgr.code == FundPortfolio.mgr_code')
```
完整代码参考：[此处](https://github.com/imoyao/fundmate/blob/5723c8304be87c5bde040c0716b8c407c860bea7/backend/fundmate/fund/models.py#L477)
该方法可以在不使用架构级别的外键设计的同时很方便地将对象关联起来。其中`primaryjoin`参数为两个表的关联条件。
::: warning
在封装内部，会调用`eval()`方法作为查询条件。正如我们知道的那样，不要将不信任的字符传入其中。
:::
之后，我们可以通过以下方式查询组合信息：
```python
fpo = FundPortfolio.query.filter_by(portfolio_code=portfolio_code).one_or_none()
```
组合管理者信息使用`fpo.manager`获取。

4. 同时与两个表关联的设计

在本系统设计中，我们的组合维护有两种数据来源：a)由程序从第三方网站中自动获取；b)平台内部用户自己创建并维护组合；对于平台内部用户创建的组合，我们的用户信息在 User 表中已经有保存。

为了解决用户信息获取，我们可以：a)简单将用户信息复制一份，这样会导致用户数据重复，且后期维护时需要维护两份数据；b)将 3 个表关联起来，这样在编写代码时需要建立两个`relationship`关系。我们尝试编写如下代码将`FundPortfolio`与`User`关联： 
```python
extra_owner = relationship('User', foreign_keys=[mgr_code], primaryjoin='User.id == FundPortfolio.mgr_code')
```
完整代码参考：[此处](https://github.com/imoyao/fundmate/blob/5723c8304be87c5bde040c0716b8c407c860bea7/backend/fundmate/fund/models.py#L483)

不过，我们在`fund.models`导入`user.models.User`定义并引用时会报错：
```python
sqlalchemy.exc.InvalidRequestError: When initializing mapper mapped class FundPortfolio->fund_portfolio, expression 'User.id == FundPortfolio.mgr_code' failed to locate a name ("name 'User' is not defined"). If this is a class name, consider adding this relationship() to the <class 'backend.fundmate.fund.models.FundPortfolio'> class after both dependent classes have been defined.
```
这段话中提示`User`定义未找到，看来两个数据类（`User`和`FundPortfolio`）不在同一个`models.py`文件内这样引用，代码是无法找到数据类定义的！

不过，经过测试，我们这么写是可以的：
```python
class FundPortfolio(PkModel, CreateDateModel, UpsertMixin):
    ...
    
    @property
    def manager(self):  # 示例代码中为了避免命名空间重复问题，我们将方法定义为`managers`
        """
        使用装饰器方法变属性
        :return:
        """
        if self.platform != 'own':
            return FundPortfolioMgr.query.filter_by(code=self.mgr_code).one_or_none()
        else:
            mgr_id = int(self.mgr_code)
            user = User.query.filter_by(id=mgr_id).one_or_none()
            return user
```
完整代码参考：[此处](https://github.com/imoyao/fundmate/blob/5723c8304be87c5bde040c0716b8c407c860bea7/backend/fundmate/fund/models.py#L490)

但是，考虑到数据类设计的问题，在后续序列化输出的时候，可能我们没法很好地定义。

此外，或许~~我们可以尝试将数据定义类放在一起~~。但是考虑到代码结构设计的问题，我们没有继续探索这条路线的可行性。

5. 如何解决这种让人纠结的状况？

首先，我们还是回到第 3 步中的定义。此时，将`FundPortfolioMgr`与`FundPortfolio`关联起来是没有问题的，不过需要将查询条件更准确一点：
```python
class FundPortfolio(PkModel, CreateDateModel, UpsertMixin):
    ...
    manager = relationship('FundPortfolioMgr',
                       foreign_keys=[mgr_code],
                       primaryjoin='and_(FundPortfolioMgr.code == FundPortfolio.mgr_code, FundPortfolio.platform!=4)')
```
在`@output`端的`FundPortfolioDetailOutSchema`定义中，我们可以增加`extra_owner`字段的定义用于获取自有平台用户创建的组合的信息。
```python

def internal_fpo_manager(obj):
    """
    内部用户自建组合的用户信息从`User`表中获取
    :param obj:
    :return:
    """
    if not obj.manager and obj.platform == 'own':
        mgr_id = int(obj.mgr_code)
        user = User.query.filter_by(id=mgr_id).one_or_none()

        # [Custom Fields — marshmallow 3.14.1 documentation](
        # https://marshmallow.readthedocs.io/en/stable/custom_fields.html) BlogSchema().dump(blog)
        return FundPortfolioWithUserOutSchema().dump(user)


class FundPortfolioDetailOutSchema(Schema):
    ...
    extra_owner = Function(lambda obj: internal_fpo_manager(obj))
    
```
同时，我们可以和前端约定：优先从`manager`字段中获取数据，如果信息为空，则去`extra_owner`中获取维护者信息。

参阅：
2. [Custom Fields — marshmallow 3.14.1 documentation](https://marshmallow.readthedocs.io/en/stable/custom_fields.html)