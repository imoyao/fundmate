# -*- coding: utf-8 -*-
"""User views."""
from apiflask import Schema, input, output, abort, APIBlueprint
from apiflask.fields import Integer, String, Date, Number, Function, Nested
from apiflask.validators import Length, Range
from flask.views import MethodView

from backend.fundmate.view_ext import paginate_query
from backend.fundmate.fund.models import Fund, FundMgr, FundCompany, FundSaleOrg

bp = APIBlueprint("fund", __name__, url_prefix="/funds")


class FundOutSchema(Schema):
    id = Integer()
    name = String()
    mgr = String()
    fund_code = String()
    created_at = Date()
    company = String()
    fund_type = String()


class FundMgrOutSchema(Schema):
    id = Integer()
    name = String()
    mgr_code = String()
    created_at = Date()
    company = String()


class EmptySchema(Schema):
    pass


class FundCompanyOutSchema(Schema):
    id = Integer()
    code = String()
    name = String()
    full_name = String()
    tx_eval = Integer()
    create_date = Date()
    scale = Number()


class FundInSchema(Schema):
    code = String(validate=Length(5, 25))
    name = String(validate=Length(6, 40))


class QuerySchema(Schema):
    page = Integer(missing=1)
    per_page = Integer(missing=20, validate=Range(max=30))


@bp.route('/')
class Funds(MethodView):
    @input(QuerySchema, 'query')
    @output(FundOutSchema)
    def get(self, query):
        ret = paginate_query(Fund, query)
        return ret

    @output(FundOutSchema(many=True))
    def get(self):
        ret = Fund.query.order_by(Fund.fund_code.desc()).all()
        return ret


@bp.route('/companies/')
class FundCompanyView(MethodView):

    @input(QuerySchema, 'query')
    @input(EmptySchema)
    @output(FundCompanyOutSchema(many=True))
    def get(self, query: dict = None):
        """
        获取基金公司信息
        """
        if query:
            ret = paginate_query(FundCompany, query)
        else:
            ret = FundCompany.query.order_by(FundCompany.scale.desc()).all()
        return ret


@bp.route('/mgrs/')
class FundMgrView(MethodView):

    @input(QuerySchema, 'query')
    @input(EmptySchema)
    @output(FundOutSchema)
    def get(self, query: dict = None):
        if query:
            ret = paginate_query(FundMgr, query)
        else:
            ret = Fund.query.all()
        return ret


class SaleSchema(Schema):
    class Meta:
        fields = ('id', 'name')


class FundSaleOutSchema(Schema):
    # [python - Is it possible to use a schema for a marshmallow custom field? - Stack Overflow](https://stackoverflow.com/questions/49802142/is-it-possible-to-use-a-schema-for-a-marshmallow-custom-field)
    id = String()
    name = Function(lambda obj: SaleSchema(many=True).dump(obj.as_name()))


@bp.route('/sales/')
class FundSalesView(MethodView):

    @input(QuerySchema, 'query')
    @input(EmptySchema)
    @output(FundSaleOutSchema)
    def get(self, query: dict = None):
        if query:
            ret = paginate_query(FundSaleOrg, query)
        else:
            ret = FundSaleOrg.query.groupby(FundSaleOrg.org_type)
        return ret


@bp.route('/<int:fund_id>')
class FundDetail(MethodView):
    """
    基金详情
    """

    @output(FundOutSchema)
    def get(self, fund_id: str):
        """获取指定基金信息"""
        user_obj = Fund.get_by_id(int(fund_id))
        return user_obj

    def post(self):
        """
        新建基金
        """
        return {'message': 'Hello,User!'}

    @input(FundInSchema(partial=True))
    @output(FundOutSchema)
    def patch(self, fund_id, data):
        """获取指定基金信息"""
        _user_obj = Fund.get_by_id(int(fund_id))
        if _user_obj:
            abort(404)
        user = Fund.save(data)
        return user
