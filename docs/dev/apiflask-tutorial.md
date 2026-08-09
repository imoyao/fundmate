---
title: ApiFlask 简易教程
---

## 分页器

借助于 SQLAlchemy 的`paginate`将查询结果实现分页，内部我们定义`CustomPaginationSchema`来序列化请求参数，需要注意的是，如果请求中有其他参数时，路径中的参数需要作为关键字参数来传递给`pagination_builder`，否则报错`werkzeug.routing.BuildError: Could not build url for endpoint 'fund.PortfoliosAdjust' with values ['page', 'per_page']. Did you forget to specify values ['portfolio_code']?
`。示例代码：

```python
@bp.route('/portfolios/<string:portfolio_code>/adjustments')
class PortfoliosAdjust(MethodView):
    """
    单一组合调仓信息
    """

    @input(CustomPaginationSchema, 'query')
    @output(FundPortfoliosAdjustOutSchema)
    def get(self, portfolio_code: str, query: dict):
        ...
        portfolios = pagination.items
        return {'adjusts': portfolios, 'pagination': pagination_builder(pagination, portfolio_code=portfolio_code)}
```
